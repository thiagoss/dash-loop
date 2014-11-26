import itertools
import os
from xml.etree import ElementTree


DASH_NAMESPACE_RAW='urn:mpeg:DASH:schema:MPD:2011'
DASH_NAMESPACE='{' + DASH_NAMESPACE_RAW + '}'

current_dir = os.path.dirname(os.path.realpath(__file__))

ElementTree.register_namespace('', DASH_NAMESPACE_RAW)

from flask import Flask, Response, send_from_directory
app = Flask(__name__)

class DashAdaptationSet(object):
    def __init__(self, adapt_set):
        self.adaptation_set = adapt_set
        self.representations = {}
        for r in self.adaptation_set.findall(DASH_NAMESPACE + 'Representation'):
            self.representations[r.get('id')] = r

    @property
    def id(self):
        return self.adaptation_set.get('id')

    def _change_to_live(self):
        pass

    def has_representation_id(self, repr_id):
        return repr_id in self.representations

    def find_matching_fragment(self, repr_id, fragment_number):
        r = self.representations[repr_id]
        return fragment_number

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

        self._change_to_live()

    def _change_to_live(self):
        self.root.set('type', 'dynamic')
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
        for s in self.streams.itervalues():
            if s.has_representation_id(repr_id):
                path = s.find_matching_fragment(repr_id, fragment_number)
                break

        if path:
            return '%s/%s' % (repr_id, path)

mpd = DashMPD('playlist.mpd')
print mpd.get_mpd_string()

@app.route("/<string:name>.mpd")
def playlist(name):
    return Response(mpd.get_mpd_string(), mimetype="application/dash+xml")

@app.route("/<string:repr_id>/<string:fragment_number>")
def fragment(repr_id, fragment_number):
    path = mpd.find_matching_fragment(repr_id, fragment_number)
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
