import utitls
import time
import traceback
import os
import signal

from login import login
from bilibiliProxy import BilibiliProxy
from subprocessOp import _forwardStream_sync, _getYoutube_m3u8_sync, async_forwardStream
import questInfo
from myRequests import subscribe

def bilibiliStartLive(subscribe_obj, room_title, area_id=None):
    curSub = subscribe_obj
    channelId = curSub.get('youtubeChannelId', "")
    curBiliAccCookie = curSub.get('bilibili_cookiesStr', "")

    tmp_area_id = area_id
    if tmp_area_id == None:
        tmp_area_id = curSub.get('bilibili_areaid', '33')

    b = BilibiliProxy(curBiliAccCookie)
    if b.getAccInfo() == None:
        #relogin
        if curSub['login_type'] == 'account':
            tmp_username, tmp_password = curSub.get('username'), curSub.get('password')
            if tmp_username and tmp_password:
                curSub['bilibili_cookiesStr'] = login(tmp_username, tmp_password)
                utitls.setSubInfoWithSubChannelId(channelId, curSub)
                bilibiliStartLive(channelId, room_title, area_id)
                return #retry the StartLive. TODO Maybe limit the retry time?

    t_room_id = b.getLiveRoomId()
    # b.stopLive(t_room_id)   #Just don't care the Live status, JUST STARTLIVE
    # b.updateRoomTitle(t_room_id, room_title) #Maybe just ignore changing the title
    rtmp_link = b.startLive(t_room_id, tmp_area_id)

    if curSub.get('auto_send_dynamic') and rtmp_link and questInfo._getObjWithRTMPLink(rtmp_link) is None:
        if curSub.get('dynamic_template'):
            b.send_dynamic((curSub['dynamic_template']).replace('${roomUrl}', 'https://live.bilibili.com/' + t_room_id))
        else:
            b.send_dynamic('转播开始了哦~')
    return b, t_room_id, rtmp_link

__g_try_get_youtube_list = []
def Async_forwardToBilibili(subscribe_obj, input_link, room_title='Testing Title', area_id=None, isSubscribeQuest=True):
    utitls.runFuncAsyncThread(_forwardToBilibili_Sync, (subscribe_obj, input_link, room_title, area_id, isSubscribeQuest))
def _forwardToBilibili_Sync(subscribe_obj, input_link, room_title, area_id=None, isSubscribeQuest=True):
    if isSubscribeQuest:
        global __g_try_get_youtube_list
        if input_link in __g_try_get_youtube_list:
            return

        __g_try_get_youtube_list.append(input_link)
        resloveURLOK = False
        tmp_retryTime = 60 * 10      #retry 10 hours, Some youtuber will startLive before few hours
        while tmp_retryTime > 0:
            if 'youtube.com/' in input_link or 'youtu.be/' in input_link:
                m3u8Link, title, err, errcode = _getYoutube_m3u8_sync(input_link, False)
                if errcode == 999:
                    # this is just a video upload, so just finish it
                    __g_try_get_youtube_list.remove(input_link)
                    return
                elif errcode == 0:
                    # input_link = m3u8Link   #just to check is can use, _forwardStream_sync will access the title and questInfo
                    resloveURLOK = True
                    break
                else:
                    tmp_retryTime -= 1
                    time.sleep(60)
            else:
                utitls.myLogger('_forwardToBilibili_Sync LOG: Unsupport ForwardLink:' + input_link)
                __g_try_get_youtube_list.remove(input_link)
                return
    else:
        resloveURLOK = True     # if it is a direct call, just skip the retry

    if resloveURLOK:
        b, t_room_id, rtmp_link = bilibiliStartLive(subscribe_obj, room_title, area_id)
        if rtmp_link:   #kill the old proccess
            tmp_quest = questInfo._getObjWithRTMPLink(rtmp_link)
            if tmp_quest != None:
                try:
                    os.kill(tmp_quest.get('pid', None), signal.SIGKILL)
                except Exception:
                    utitls.myLogger(traceback.format_exc())
                time.sleep(5)
            # force stream
            _forwardStream_sync(input_link, rtmp_link, isSubscribeQuest)
    __g_try_get_youtube_list.remove(input_link)



def Async_subscribeTheList():
    utitls.runFuncAsyncThread(subscribeTheList_sync, ())
def subscribeTheList_sync():
    time.sleep(10)   #wait the server start preparing
    while True:
        subscribeList = utitls.configJson().get('subscribeList', [])
        ip = utitls.configJson().get('serverIP')
        port = utitls.configJson().get('serverPort')
        for item in subscribeList:
            tmp_subscribeId = item.get('youtubeChannelId', "")
            if tmp_subscribeId != "":
                tmp_callback_url = 'http://{}:{}/subscribe'.format(ip, port)
                subscribe(tmp_callback_url, tmp_subscribeId)
        time.sleep(3600 * 24 * 4)   #update the subscribe every 4 Days


def restartOldQuests():
    time.sleep(3)   #wait the server start preparing
    for quest in questInfo._getQuestList():
        rtmp_link = quest.get('rtmpLink')
        questInfo.updateQuestInfo('isRestart', True, rtmp_link)
        async_forwardStream(
            quest.get('forwardLinkOrign'),
            rtmp_link,
            quest.get('isSubscribeQuest')
        )


def preparingAllAccountsCookies():
    utitls.runFuncAsyncThread(preparingAllAccountsCookies_sync, ())
def preparingAllAccountsCookies_sync():
    time.sleep(2)   #wait the server start preparing
    sub_list = utitls.configJson().get('subscribeList', [])
    for curSub in sub_list:
        if curSub.get('login_type', "") == 'account' and curSub.get('bilibili_cookiesStr', "") == "":
            tmp_username, tmp_password = curSub.get('username'), curSub.get('password')
            if tmp_username and tmp_password:
                curSub['bilibili_cookiesStr'] = login(tmp_username, tmp_password)
                utitls.setSubInfoWithKey('username', tmp_username, curSub)
                time.sleep(5)   # wait for the last browser memory release
