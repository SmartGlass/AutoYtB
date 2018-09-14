from http.server import BaseHTTPRequestHandler
from urllib.parse import urlsplit,parse_qs
import xml.etree.ElementTree as ET
import traceback

from utitls import verifySecert, myLogger, configJson
from subprocessOp import async_forwardStream
from AutoOperate import Async_forwardToBilibili

class RequestHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        request_path = self.path
        rc = 404
        rb = None
        params = parse_qs(urlsplit(request_path).query)

        if request_path.startswith('/subscribe?'):
            hub_challenge_list = params.get('hub.challenge', None)
            if None != hub_challenge_list:
                rc = 202
                rb = hub_challenge_list[0]
        elif request_path.startswith('/live_restream?'):
            forwardLink_list = params.get('forwardLink', None)
            restreamRtmpLink_list = params.get('restreamRtmpLink', None)
            if forwardLink_list and restreamRtmpLink_list:
                tmp_forwardLink = forwardLink_list[0]
                tmp_rtmpLink = restreamRtmpLink_list[0]
                isOK = True

                if 'send.acg.tv/' in tmp_rtmpLink:
                    tmp_rtmpLink = tmp_rtmpLink + "&key=" + params.get('key', [''])[0]

                print(tmp_forwardLink, tmp_rtmpLink)
                if 'twitcasting.tv/' in tmp_forwardLink:
                    #('https://www.', 'twitcasting.tv/', 're2_takatsuki/fwer/aeqwet')
                    tmp_twitcasID = tmp_forwardLink.partition('twitcasting.tv/')[2]
                    tmp_twitcasID = tmp_twitcasID.split('/')[0]
                    print(tmp_twitcasID)

                    tmp_forwardLink = 'http://twitcasting.tv/{}/metastream.m3u8/?video=1'.format(tmp_twitcasID)
                elif tmp_forwardLink.endswith('.m3u8') or 'youtube.com/' in tmp_forwardLink or 'youtu.be/' in tmp_forwardLink:
                    tmp_forwardLink = tmp_forwardLink
                else:
                    isOK = False

                if isOK:
                    rc = 200
                    rb = 'forwardLink:{},\nrestreamRtmpLink:{}'.format(tmp_forwardLink, tmp_rtmpLink)
                    async_forwardStream(tmp_forwardLink, tmp_rtmpLink)

        self.send_response(rc)
        self.end_headers()
        if None != rb:
            self.wfile.write(rb.encode())


    def do_POST(self):
        request_path = self.path
        rc = 404
        myLogger("\n----- Request POST Start ----->\n")
        myLogger(request_path)

        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)

        myLogger(self.headers)
        myLogger(post_data)
        myLogger("<----- Request POST End -----\n")

        if '/subscribe' in request_path:
            # check the secert
            secert = self.headers.get('X-Hub-Signature', '').split('=')[1]
            if verifySecert(secert, post_data):
                try:
                    tree = ET.ElementTree(ET.fromstring(post_data.decode()))
                except Exception:
                    myLogger(traceback.format_exc())
                    self.send_response(rc)
                    self.end_headers()
                    return

                ns = {'dfns': 'http://www.w3.org/2005/Atom', 'yt': 'http://www.youtube.com/xml/schemas/2015', 'at': 'http://purl.org/atompub/tombstones/1.0'}
                root = tree.getroot()

                if root.find('dfns:title', ns) != None:
                    tmp_feedTitle = root.find('dfns:title', ns).text
                    tmp_feedUpadatedTime = root.find('dfns:updated', ns).text
                    try:
                        entry = root.findall('dfns:entry', ns)[0]       #maybe more than one?
                        tmp_entry_title = entry.find('dfns:title', ns).text
                        tmp_entry_videoId = entry.find('yt:videoId', ns).text
                        tmp_entry_channelId = entry.find('yt:channelId', ns).text
                        tmp_entry_link = entry.find('dfns:link', ns).attrib.get('href')
                        tmp_entry_publishedTime = entry.find('dfns:published', ns).text
                        tmp_entry_updatedTime = entry.find('dfns:updated', ns).text

                        myLogger("%s, %s" % (tmp_feedTitle, tmp_feedUpadatedTime))
                        myLogger("%s, %s, %s, %s, %s, %s " % (
                                    tmp_entry_title, tmp_entry_videoId, tmp_entry_channelId, tmp_entry_link, tmp_entry_publishedTime, tmp_entry_updatedTime)
                                )
                        Async_forwardToBilibili(tmp_entry_channelId, tmp_entry_link, tmp_entry_title, configJson().get('area_id'))
                    except Exception:
                        myLogger(traceback.format_exc())
                        self.send_response(rc)
                        self.end_headers()
                        return
                    rc = 204
            else:
                myLogger("verifySecert Failed with:" + secert)
            self.send_response(rc)
            self.end_headers()
        else:
            self.send_response(rc)
            self.end_headers()
