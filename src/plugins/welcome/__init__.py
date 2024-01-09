#from nonebot.adapters.onebot.v11 import Bot, Message, NoticeEvent
#from nonebot import on_notice
#
#welcom = on_notice()
#@welcom.handle() 
#async def h_r(bot: Bot, event: NoticeEvent):
#    
#    if event.notice_type == 'group_increase':
#        user = event.get_user_id()  
#        msg = f'[CQ:at,qq={user}] 加入群聊'
#        print(f'send: {msg}')
#        await welcom.finish(message=Message(f'{msg}'))
#
#    if event.notice_type == 'group_decrease':
#        user = event.get_user_id() 
#        msg = f'{user} 退出群聊'
#        print(f'send: {msg}')
#        await welcom.finish(message=Message(f'{msg}'))  