from flask import Flask, request, abort
from google.cloud import storage

from linebot import (
    LineBotApi, WebhookHandler
)
from linebot.exceptions import (
    InvalidSignatureError
)
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, FollowEvent, ImageMessage, FlexSendMessage, TemplateSendMessage,
    CameraAction, CameraRollAction, QuickReply, QuickReplyButton
)

from linebot.models.template import(
    ButtonsTemplate
)

from models.user import User
from daos.user_dao import UserDAO
from utils.reply_send_message import detect_json_array_to_new_message_array
from services.image_service import ImageService

# 圖片下載與上傳專用
import urllib.request
import os

# 建立日誌紀錄設定檔
# https://googleapis.dev/python/logging/latest/stdlib-usage.html
import logging
import google.cloud.logging
from google.cloud.logging.handlers import CloudLoggingHandler

# 啟用log的客戶端
client = google.cloud.logging.Client()


# 建立line event log，用來記錄line event
bot_event_handler = CloudLoggingHandler(client,name="seaturtle_bot_event")
bot_event_logger=logging.getLogger('seaturtle_bot_event')
bot_event_logger.setLevel(logging.INFO)
bot_event_logger.addHandler(bot_event_handler)


app = Flask(__name__)

# 參數設定
common_variable = True
if common_variable: 
    bucket_name = os.environ['USER_INFO_GS_BUCKET_NAME']
    channel_access_token = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
    channel_secret = os.environ["LINE_CHANNEL_SECRET"]
else:
    bucket_name = 'seaturtle2-linebot-user-info'
    channel_access_token = 'o6S1Y3+dTExuGzZDHuWBV8dXj9inFTlKKB3yJWwZ6u0+/hZP/Pz0mixA9tUYl4Qk/adOiTKzDcR4I0Iq9Jn0xKM0FWF35CV60x7h0iKNqQwFPRRPKhoGBW0PUXAdnA9WWNzwnLv2HYgFdv5Jps2oBQdB04t89/1O/w1cDnyilFU='
    channel_secret = '9accedd3c1ac3921b3b8d59c499c0c18'

setmenu = 0

# 註冊機器人
line_bot_api = LineBotApi(channel_access_token)
handler = WebhookHandler(channel_secret)

# 設定機器人訪問入口
@app.route("/callback", methods=['POST'])
def callback():
    # get X-Line-Signature header value
    signature = request.headers['X-Line-Signature']

    # get request body as text
    body = request.get_data(as_text=True)
    print(body)
    # 消息整個交給bot_event_logger，請它傳回GCP
    bot_event_logger.info(body)
    # handle webhook body
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        print("Invalid signature. Please check your channel access token/channel secret.")
        abort(400)

    return 'OK'

# 先確保還沒有任何圖文選單
rich_menu_list = line_bot_api.get_rich_menu_list()
for rich_menu in rich_menu_list:
    line_bot_api.delete_rich_menu(rich_menu.rich_menu_id)


# 設定圖文選單和載入圖片
from linebot.models import RichMenu
import requests
import json

menufile = 'richmenu/menuraw1.json'
menuimage = 'richmenu/menu1.jpg'

with open(menufile, 'r', encoding='utf-8') as f:
    menuJson = json.load(f)

lineRichMenuId = line_bot_api.create_rich_menu(rich_menu=RichMenu.new_from_json_dict(menuJson))

with open(menuimage, 'rb') as uploadImage:
    line_bot_api.set_rich_menu_image(lineRichMenuId, 'image/jpeg', uploadImage)

# 當加入好友時
@handler.add(FollowEvent)
def handle_line_follow(event):
    # 取個資
    line_user_profile = line_bot_api.get_profile(event.source.user_id)

    # 將個資轉換成user
    user = User(
        line_user_id=line_user_profile.user_id,
        line_user_pic_url=line_user_profile.picture_url,
        line_user_nickname=line_user_profile.display_name,
        line_user_status=line_user_profile.status_message,
        line_user_system_language=line_user_profile.language,
        blocked=False
    )

    # 確定執行到這邊
    print('取到用戶個資了')

    # 綁定圖文選單
    try:
        line_bot_api.link_rich_menu_to_user(user.line_user_id, lineRichMenuId)
        print('綁定圖文選單')
    except:
        print('綁定圖文選單失敗')

    # 歡迎問候和暖身小遊戲
    greeting = f'哈囉，{user.line_user_nickname}您好！'
    result_message_array = detect_json_array_to_new_message_array('welcome_message_json/welcome2.json')
    line_bot_api.reply_message(
        event.reply_token,
        [TextSendMessage(text=greeting)] + result_message_array
    )

    # 確定執行到這邊
    #print('到發送歡迎訊息階段')

    '''
    先確認用戶的照片連結是否正常，若存在，取得用戶照片，存放回cloud storage 並將連結存回user的連結
    '''
    if user.line_user_pic_url is not None:
        # 跟line 取回照片，並放置在本地端
        file_name = user.line_user_id + '.jpg'
        urllib.request.urlretrieve(user.line_user_pic_url, file_name)
        
        # 上傳至bucket
        try:
            storage_client = storage.Client()
            destination_blob_name = f'{user.line_user_id}/user_pic.png'
            bucket = storage_client.bucket(bucket_name)
            blob = bucket.blob(destination_blob_name)
            blob.upload_from_filename(file_name)
        except:
            print('上傳 Stoarge 發生錯誤')

        # 更新回user的圖片連結
        destination_url = f'https://storage.googleapis.com/{bucket_name}/{user.line_user_id}/user_pic.png'
        user.line_user_pic_url = destination_url

        # 確定執行到這邊
        #print('上傳 Storage 完成')

    # 存入資料庫
    UserDAO.save_user(user)

    # 確定執行到這邊
    #print('存入用戶資料 firestore 完成')

'''
創建 QuickReply 給幫你龜類
'''
# 點擊後開啟相機, 給用戶拍照後發送圖片
cameraQuickReplyButton = QuickReplyButton(
    action=CameraAction(label="拍照")
)

## 點擊後，切換至照片相簿選擇
# 發圖片消息給我方
cameraRollQRB = QuickReplyButton(
    action=CameraRollAction(label="選擇照片")
)

'''
以QuickReply封裝那些QuickReply Button
'''
## 設計QuickReplyButton的List
quickReplyList = QuickReply(
    items = [cameraQuickReplyButton, cameraRollQRB]
)

'''
製作TextSendMessage，並將剛封裝的QuickReply放入
'''
## 將quickReplyList 塞入TextSendMessage 中
quick_reply_text_send_message = TextSendMessage(text='拍照上傳或選擇圖片，幫你龜類', quick_reply=quickReplyList)

# 特殊文字指令
template_message_dict = {
  "@龜去來戲": TextSendMessage(text="此功能尚未完成，敬請期待!!"),
  "@世界龜寶": detect_json_array_to_new_message_array('data_message_json/data2_message.json'),
  "@幫你龜類": quick_reply_text_send_message,
  "@我的龜密": detect_json_array_to_new_message_array('data_message_json/data4_message.json'),
  "@殊途同龜": detect_json_array_to_new_message_array('data_message_json/data5_message.json'),
  "@默守成龜": detect_json_array_to_new_message_array('data_message_json/data6_message.json'), 
}

# 當用戶收到文字消息的時候，回傳用戶講過的話
@handler.add(MessageEvent, message=TextMessage)
def handle_line_text(event):
    if(event.message.text.find('@')!= -1):
        line_bot_api.reply_message(
        event.reply_token,
        #buttons_template_message
        #detect_json_array_to_new_message_array('test_message_json/flex_message.json')
        #TextSendMessage(text="特殊功能")
        template_message_dict.get(event.message.text)
        )
    # elif(event.message.text.find('#')!=-1):
    #     line_bot_api.link_rich_menu_to_user(event.source.user_id, lineRichMenuId)
    #     line_bot_api.reply_message(
    #         event.reply_token,
    #         TextSendMessage(text='圖文選單')
    #    )
    # 請line_bot_api回應，回應用戶講過的話
    else:
        if setmenu == 0:
            line_bot_api.link_rich_menu_to_user(event.source.user_id, lineRichMenuId)
            setmenu += 1
        
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=event.message.text))

# 當用戶收到圖片進行辨識
@handler.add(MessageEvent,ImageMessage)
def handle_line_image(event):
    ImageService.line_user_upload_image(event)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))