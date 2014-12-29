import itertools
import os
from xml.etree import ElementTree
from datetime import datetime, timedelta

DASH_NAMESPACE_RAW='urn:mpeg:DASH:schema:MPD:2011'
DASH_NAMESPACE='{' + DASH_NAMESPACE_RAW + '}'

current_dir = os.path.dirname(os.path.realpath(__file__))

ElementTree.register_namespace('', DASH_NAMESPACE_RAW)

from flask import Flask, Response, send_from_directory
app = Flask(__name__)

def count_files(path):
    fullpath = os.path.join(current_dir, path)
    return len([name for name in os.listdir(fullpath) if os.path.isfile(os.path.join(fullpath, name))])

class DashAdaptationSet(object):
    def __init__(self, adapt_set):
        self.adaptation_set = adapt_set
        template = adapt_set.findall(DASH_NAMESPACE + 'SegmentTemplate')[0]
        self.segment_duration = float(template.get('duration')) / float(template.get('timescale'))
        self.representations = {}
        for r in self.adaptation_set.findall(DASH_NAMESPACE + 'Representation'):
            data = {}
            data['node'] = r
            data['fragments-count'] = count_files(r.get('id')) - (1 if self.has_initialization_segment() else 0)

            self.representations[r.get('id')] = data

    @property
    def id(self):
        return self.adaptation_set.get('id')

    def has_initialization_segment(self):
        segtemplate = self.adaptation_set.find(DASH_NAMESPACE + 'SegmentTemplate')
        return 'initialization' in segtemplate.attrib

    def _change_to_live(self):
        pass

    def has_representation_id(self, repr_id):
        return repr_id in self.representations

    def find_matching_fragment(self, repr_id, fragment_number):
        r = self.representations[repr_id]
        try:
            fragment_number = int(fragment_number)
        except ValueError:
            return fragment_number, 0.0

        return ((fragment_number - 1) % r['fragments-count']) + 1, fragment_number * self.segment_duration

class DashMPD(object):
    def __init__(self, path_to_mpd):
        self.tree = ElementTree.parse(path_to_mpd)
        self.root = self.tree.getroot()
        if self.root.tag != (DASH_NAMESPACE + 'MPD'):
            raise Exception, "Not an MPD"
        period = self.root.findall(DASH_NAMESPACE + 'Period')
        if len(period) != 1:
            raise Exception, "Only one period supported"
        period = period[0]

        self.streams = {}
        for adaptationset in period.findall(DASH_NAMESPACE + 'AdaptationSet'):
            adapt_info = DashAdaptationSet(adaptationset)
            self.streams[adapt_info.id] = adapt_info

        self.start_time = datetime.utcnow()
        self._change_to_live()

    def _change_to_live(self):
        self.root.set('type', 'dynamic')
        try:
            del self.root.attrib['mediaPresentationDuration']
        except:
            pass
        self.root.set('availabilityStartTime', self.start_time.isoformat())

        period = self.root.find(DASH_NAMESPACE + 'Period')
        try:
            del period.attrib['duration']
        except:
            pass
        for s in self.streams.itervalues():
            s._change_to_live()

    def get_mpd_string(self):
        return ElementTree.tostring(self.root, encoding='utf8', method='xml')

    def find_matching_fragment(self, repr_id, fragment_number):
        path = None
        ts = None
        for s in self.streams.itervalues():
            if s.has_representation_id(repr_id):
                path, ts = s.find_matching_fragment(repr_id, fragment_number)
                break

        if path:
            if timedelta(0, ts) + self.start_time <= datetime.utcnow():
                return '%s/%s' % (repr_id, path)
        return None

mpd = DashMPD('playlist.mpd')
print mpd.get_mpd_string()

@app.route("/<string:name>.mpd")
def playlist(name):
    return Response(mpd.get_mpd_string(), mimetype="application/dash+xml")

@app.route("/<string:repr_id>/<string:fragment_number>")
def fragment(repr_id, fragment_number):
    path = mpd.find_matching_fragment(repr_id, fragment_number)
    if not path:
        return '', 404
    return send_from_directory(current_dir, path)

def crossdomain():
    return Response("""<cross-domain-policy>
<site-control permitted-cross-domain-policies="all"/>
<allow-access-from domain="*" secure="false"/>
<allow-http-request-headers-from domain="*" headers="*" secure="false"/>
</cross-domain-policy>""", mimetype="text/xml")

if __name__ == "__main__":
    app.debug = True
    app.run(host='0.0.0.0')
