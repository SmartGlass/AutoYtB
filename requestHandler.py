from http.server import BaseHTTPRequestHandler
from urllib.parse import urlsplit,parse_qs
import xml.etree.ElementTree as ET
import traceback
import json
import os
import signal
import zlib
from mimetypes import types_map

import utitls
from subprocessOp import async_forwardStream
from AutoOperate import Async_forwardToBilibili

from questInfo import checkIfInQuest, getQuestListStr, getQuestList_AddStarts, updateQuestInfo, _getObjWithRTMPLink


class RequestHandler(BaseHTTPRequestHandler):

    def gzip_encode(self, content):
        gzip_compress = zlib.compressobj(9, zlib.DEFLATED, zlib.MAX_WBITS | 16)
        data = gzip_compress.compress(content) + gzip_compress.flush()
        return data

    def do_GET(self):
        request_path = self.path
        rc = 404
        rb = None
        sh = {
            'Content-Encoding': 'gzip'
        }
        params = parse_qs(urlsplit(request_path).query)

        try:
            if request_path.startswith('/web/'):
                request_path = request_path.split('?')[0]
                fname, ext = os.path.splitext(request_path)
                if ext in (".html", ".css", ".js"):
                    tmp_filePath = os.path.join(os.getcwd())
                    for v in request_path.split('/'):
                        tmp_filePath = os.path.join(tmp_filePath, v)
                    with open(tmp_filePath, 'r', encoding='utf-8') as f:
                        lastMtime = self.date_time_string(os.fstat(f.fileno()).st_mtime)
                        if self.headers.get('If-Modified-Since') == lastMtime:
                            self.send_response(304)
                            self.end_headers()
                            return

                        self.send_response(200)
                        sh['Content-type'] = types_map[ext]
                        sh['Cache-Control'] = 'max-age=72000'
                        fb = f.read()
                        rb = self.gzip_encode(fb.encode('utf-8'))
                        sh['Content-length'] = len(rb)
                        sh['Last-Modified'] = lastMtime
                        for key in sh:
                            self.send_header(key, sh[key])
                        self.end_headers()
                        self.wfile.write(rb)
                return
        except Exception:
            utitls.myLogger(traceback.format_exc())
            self.send_error(404)
            self.end_headers()
            return

        if request_path.startswith('/get_manual_json'):
            rc = 200
            ret_dic = utitls.manualJson()
            ret_dic['des_dict'] = []    #clear the des

            tmp_acc_mark_list = []
            for sub in utitls.configJson().get('subscribeList', []):
                tmp_mark = sub.get('mark')
                if tmp_mark:
                    tmp_acc_mark_list.append(tmp_mark)
            ret_dic['acc_mark_list'] = tmp_acc_mark_list
            rb = json.dumps(ret_dic)
        elif request_path.startswith('/questlist'):
            rc = 200
            rb = json.dumps(getQuestList_AddStarts())
        elif request_path.startswith('/live_restream?'):
            forwardLink_list = params.get('forwardLink', None)
            restreamRtmpLink_list = params.get('restreamRtmpLink', None)
            if forwardLink_list and restreamRtmpLink_list:
                tmp_forwardLink = forwardLink_list[0].strip()
                tmp_rtmpLink = restreamRtmpLink_list[0].strip()

                if 'rtmp://' in tmp_rtmpLink:
                    if utitls.checkIsSupportForwardLink(tmp_forwardLink):
                        isForwardLinkFormateOK = True
                    else:
                        isForwardLinkFormateOK = False

                    rc = 200
                    if isForwardLinkFormateOK:
                        if checkIfInQuest(tmp_rtmpLink) == False:
                            #try to restream
                            async_forwardStream(tmp_forwardLink, tmp_rtmpLink, False)
                            rb = json.dumps({"code": 0, "msg": "请求成功。请等待大概30秒，网络不好时程序会自动重试30次。也可以查看任务状态看是否添加成功。\
                                            \nRequesting ForwardLink: {},\nRequesting RestreamRtmpLink: {}\n\n".format(tmp_forwardLink, tmp_rtmpLink)})
                        else:
                            rb = json.dumps({"code": 1, "msg": "当前推流已经在任务中. \nRequesting ForwardLink: {},\nRequesting RestreamRtmpLink: {}\n\n\n-----------------CurrentQuests：\n{}".format(tmp_forwardLink, tmp_rtmpLink, getQuestListStr())})
                    else:
                        rb = json.dumps({"code": -3, "msg": "来源地址格式错误, 请查看上面支持的格式"})
                elif tmp_rtmpLink.startswith('ACCMARK='):
                    params = parse_qs(tmp_rtmpLink)
                    acc_list = params.get('ACCMARK', None)
                    opt_code_list = params.get('OPTC', None)
                    is_send_dynamic_list = params.get('SEND_DYNAMIC', None)

                    rc = 200
                    if acc_list and opt_code_list:
                        acc_mark = acc_list[0].strip()
                        opt_code = opt_code_list[0].strip()
                        is_send_dynamic = is_send_dynamic_list[0].strip()


                        tmp_is_acc_exist = False
                        for sub in utitls.configJson().get('subscribeList', []):
                            tmp_mark = sub.get('mark', "")
                            if tmp_mark == acc_mark:
                                if opt_code == sub.get('opt_code', ""):
                                    tmp_is_acc_exist = True
                                    sub['auto_send_dynamic'] = True if is_send_dynamic == '1' else False
                                    Async_forwardToBilibili(sub, tmp_forwardLink, isSubscribeQuest=False)
                                break

                        if tmp_is_acc_exist:
                            rb = json.dumps({"code": 0, "msg": "请求成功。请等待大概30秒，网络不好时程序会自动重试30次。也可以查看任务状态看是否添加成功。\
                                            \nRequesting ForwardLink: {},\nRequesting RestreamRtmpLink: {}\n\n".format(tmp_forwardLink, tmp_rtmpLink)})
                        else:
                            rb = json.dumps({"code": -5, "msg": "当前账号不存在或者账号操作码错误：{}".format(acc_mark)})

                else:
                    rc = 200
                    rb = json.dumps({"code": -4, "msg": "RTMPLink格式错误!!! bilibili的RTMPLink格式是两串合起来。\nEXAMPLE：rtmp://XXXXXX.acg.tv/live-js/?streamname=live_XXXXXXX&key=XXXXXXXXXX"})
        elif request_path.startswith('/kill_quest?'):
            rc = 200
            tmp_rtmpLink_list = params.get('rtmpLink', None)
            if tmp_rtmpLink_list:
                tmp_rtmpLink = tmp_rtmpLink_list[0].strip()
                tmp_quest = _getObjWithRTMPLink(tmp_rtmpLink)
                if tmp_quest != None:
                    try:
                        os.kill(tmp_quest.get('pid', None), signal.SIGKILL)
                        rb = json.dumps({"code": 0, "msg": "操作成功"})
                    except Exception:
                        updateQuestInfo('isDead', True, tmp_rtmpLink)
                        rb = json.dumps({"code": 1, "msg": "当前任务正在重试连接中，下次任务重试连接时会自动删除此任务"})
                else:
                    rb = json.dumps({"code": -1, "msg": "查找不到对应的任务：{}，操作失败!!".format(tmp_rtmpLink)})
        elif request_path.startswith('/addRestreamSrc?'):
            rc = 200
            srcNote_list = params.get('srcNote', None)
            srcLink_list = params.get('srcLink', None)
            if srcNote_list and srcLink_list:
                tmp_srcNote = srcNote_list[0].strip()
                tmp_srcLink = srcLink_list[0].strip()
                utitls.addManualSrc(tmp_srcNote, tmp_srcLink)
            rb = json.dumps({"code": 0, "msg":"添加成功"})
        elif request_path.startswith('/addRtmpDes?'):
            rc = 200
            rtmpNote_list = params.get('rtmpNote', None)
            rtmpLink_list = params.get('rtmpLink', None)
            if rtmpNote_list and rtmpLink_list:
                tmp_rtmpNote = rtmpNote_list[0].strip()
                tmp_rtmpLink = rtmpLink_list[0].strip()
                utitls.addManualDes(tmp_rtmpNote, tmp_rtmpLink)
            rb = json.dumps({"code": 0, "msg":"添加成功"})
        elif request_path.startswith('/subscribe?'):
            hub_challenge_list = params.get('hub.challenge', None)
            if None != hub_challenge_list:
                rc = 202
                rb = hub_challenge_list[0]


#######
        if rb:
            rb = self.gzip_encode(rb.encode('utf-8'))
            sh['Content-length'] = len(rb)

        self.send_response(rc)
        for key in sh:
            self.send_header(key, sh[key])
        self.end_headers()

        if None != rb:
            try:
                self.wfile.write(rb)
            except Exception:
                print(traceback.format_exc())


###############################################################


    def do_POST(self):
        request_path = self.path
        rc = 404
        utitls.myLogger("\n----- Request POST Start ----->\n")
        utitls.myLogger(request_path)

        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)

        utitls.myLogger(self.headers)
        utitls.myLogger(post_data)
        utitls.myLogger("<----- Request POST End -----\n")

        if '/subscribe' in request_path:
            # check the secert
            secert = self.headers.get('X-Hub-Signature', '').split('=')[1]
            if utitls.verifySecert(secert, post_data):
                try:
                    tree = ET.ElementTree(ET.fromstring(post_data.decode()))
                except Exception:
                    utitls.myLogger(traceback.format_exc())
                    self.send_response(rc)
                    self.end_headers()
                    return

                ns = {'dfns': 'http://www.w3.org/2005/Atom', 'yt': 'http://www.youtube.com/xml/schemas/2015', 'at': 'http://purl.org/atompub/tombstones/1.0'}
                root = tree.getroot()

                if root.find('dfns:title', ns) != None:
                    tmp_feedTitle = root.find('dfns:title', ns).text
                    tmp_feedUpadatedTime = root.find('dfns:updated', ns).text
                    try:
                        rc = 204
                        entry = root.findall('dfns:entry', ns)[0]       #maybe more than one?
                        tmp_entry_title = entry.find('dfns:title', ns).text
                        tmp_entry_videoId = entry.find('yt:videoId', ns).text
                        tmp_entry_channelId = entry.find('yt:channelId', ns).text
                        tmp_entry_link = entry.find('dfns:link', ns).attrib.get('href')
                        tmp_entry_publishedTime = entry.find('dfns:published', ns).text
                        tmp_entry_updatedTime = entry.find('dfns:updated', ns).text

                        utitls.myLogger("%s, %s" % (tmp_feedTitle, tmp_feedUpadatedTime))
                        utitls.myLogger("%s, %s, %s, %s, %s, %s " % (
                                    tmp_entry_title, tmp_entry_videoId, tmp_entry_channelId, tmp_entry_link, tmp_entry_publishedTime, tmp_entry_updatedTime)
                                )
                        #try to restream
                        tmp_subscribe_obj = utitls.getSubWithKey('youtubeChannelId', tmp_entry_channelId)
                        Async_forwardToBilibili(tmp_subscribe_obj, tmp_entry_link, tmp_entry_title, utitls.configJson().get('area_id'))
                    except Exception:
                        rc = 404
                        utitls.myLogger(traceback.format_exc())
            else:
                utitls.myLogger("verifySecert Failed with:" + secert)
        self.send_response(rc)
        self.end_headers()
