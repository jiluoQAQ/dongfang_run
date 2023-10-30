from hoshino import Service, R
from hoshino.typing import *
from hoshino import Service, priv, util
from hoshino.util import DailyNumberLimiter, pic2b64, concat_pic, silence
import sqlite3, os, random, asyncio
from hoshino import Service
from hoshino.typing import CQEvent
import random
import imageio
import numpy as np
import heapq
from . import _pcr_data
import time
import math
import nonebot
from . import runchara
import copy
from moviepy.editor import *
import cv2
import os
from PIL import Image,ImageFont,ImageDraw
from io import BytesIO
import base64
from .CECounter import *

sv = Service('pcr-run', enable_on_default=True)

ROAD = '='
ROADLENGTH = 15
TOTAL_NUMBER = 12
NUMBER = 5
ONE_TURN_TIME = 3
SUPPORT_TIME = 30
SLEEP_TIME = 10 #消息撤回间隔
DB_PATH = os.path.expanduser('~/.hoshino/pcr_running_counter.db')
FILE_PATH = os.path.dirname(__file__)
#如果此项为True，则技能由图片形式发送，减少风控。
SKILL_IMAGE = True
class RunningJudger:
    def __init__(self):
        self.on = {}
        self.support = {}
        self.xiazhu = {}
    def set_support(self,gid):
        self.support[gid] = {}
    def get_support(self,gid):
        return self.support[gid] if self.support.get(gid) is not None else 0
    def add_support(self,gid,uid,id,score):
        self.support[gid][uid]=[id,score]
    def get_support_id(self,gid,uid):
        if self.support[gid].get(uid) is not None:
            return self.support[gid][uid][0]
        else :
            return 0
    def get_support_score(self,gid,uid):
        if self.support[gid].get(uid) is not None:
            return self.support[gid][uid][1]
        else :
            return 0
    def get_on_off_status(self, gid):
        return self.on[gid] if self.on.get(gid) is not None else False
    def turn_on(self, gid):
        self.on[gid] = True
    def turn_off(self, gid):
        self.on[gid] = False
    def get_xiazhu_on_off_status(self, gid):
        return self.xiazhu[gid] if self.xiazhu.get(gid) is not None else False
    def xiazhu_on(self, gid):
        self.xiazhu[gid] = True
    def xiazhu_off(self, gid):
        self.xiazhu[gid] = False
    
        
                       
running_judger = RunningJudger()

class ScoreCounter:
    def __init__(self):
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        self._create_table()
        self._create_pres_table()

    def _connect(self):
        return sqlite3.connect(DB_PATH)


    def _create_table(self):
        try:
            self._connect().execute('''CREATE TABLE IF NOT EXISTS SCORECOUNTER
                          (GID             INT    NOT NULL,
                           UID             INT    NOT NULL,
                           SCORE           INT    NOT NULL,
                           PRIMARY KEY(GID, UID));''')
        except:
            raise Exception('创建表发生错误')
            
    #记录国王声望数据
    def _create_pres_table(self):
        try:
            self._connect().execute('''CREATE TABLE IF NOT EXISTS PRESTIGECOUNTER
                          (GID             INT    NOT NULL,
                           UID             INT    NOT NULL,
                           PRESTIGE           INT    NOT NULL,
                           PRIMARY KEY(GID, UID));''')
        except:
            raise Exception('创建表发生错误')
    
    
    def _add_score(self, gid, uid ,score):
        try:
            current_score = self._get_score(gid, uid)
            inscore = math.ceil(current_score+score)
            conn = self._connect()
            conn.execute("INSERT OR REPLACE INTO SCORECOUNTER (GID,UID,SCORE) \
                                VALUES (?,?,?)", (gid, uid, inscore))
            conn.commit()       
        except:
            raise Exception('更新表发生错误')

    def _reduce_score(self, gid, uid ,score):
        try:
            current_score = self._get_score(gid, uid)
            if current_score >= score:
                inscore = math.ceil(current_score-score)
                conn = self._connect()
                conn.execute("INSERT OR REPLACE INTO SCORECOUNTER (GID,UID,SCORE) \
                                VALUES (?,?,?)", (gid, uid, inscore))
                conn.commit()     
            else:
                conn = self._connect()
                conn.execute("INSERT OR REPLACE INTO SCORECOUNTER (GID,UID,SCORE) \
                                VALUES (?,?,?)", (gid, uid, 0))
                conn.commit()     
        except:
            raise Exception('更新表发生错误')
            
    def _get_prestige(self, gid, uid):
        try:
            r = self._connect().execute("SELECT PRESTIGE FROM PRESTIGECOUNTER WHERE GID=? AND UID=?", (gid, uid)).fetchone()
            return 0 if r is None else r[0]
        except:
            raise Exception('查找声望发生错误')
    
    def _add_prestige(self, gid, uid, num):
        prestige = self._get_prestige(gid, uid)
        prestige += num
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO PRESTIGECOUNTER (GID, UID, PRESTIGE) VALUES (?, ?, ?)",
                (gid, uid, prestige),
            )
    
    def _get_score(self, gid, uid):
        try:
            r = self._connect().execute("SELECT SCORE FROM SCORECOUNTER WHERE GID=? AND UID=?",(gid,uid)).fetchone()        
            return 0 if r is None else r[0]
        except:
            raise Exception('查找表发生错误')
            
#判断金币是否足够下注
    def _judge_score(self, gid, uid ,score):
        try:
            current_score = self._get_score(gid, uid)
            if current_score >= score:
                return 1
            else:
                return 0
        except Exception as e:
            raise Exception(str(e))
    

#这个类用于记录一些与技能有关的变量
class NumRecord:
    def __init__(self):
        self.kan_num = {}
        self.kokoro_num = {}
        
    def init_num(self,gid):
        self.kan_num[gid] = 1
        self.kokoro_num[gid] = 0
    def get_kan_num(self,gid): 
        return self.kan_num[gid] 
    def add_kan_num(self,gid,num):
        self.kan_num[gid]+=num
    def set_kokoro_num(self,gid,kokoro_id):
        l1 = range(1,NUMBER+1)
        list(l1).remove(kokoro_id)
        self.kokoro_num[gid] = random.choice(l1)
        return self.kokoro_num[gid]
    def get_kokoro_num(self,gid):
        return self.kokoro_num[gid]
        
numrecord = NumRecord()       

#增加角色经验
# def add_exp(gid,uid,cid,exp):
    # CE = CECounter()
    # now_level = CE._get_card_level(gid, uid, cid)
    # level_flag = 0
    # need_exp = (now_level+1)*100
    # exp_info = CE._get_card_exp(gid, uid, cid)
    # now_exp = exp_info + exp
    # if now_level>=120:
        # level_flag = 1
        # last_exp = now_exp
        # now_exp = 0
    # while now_exp>=need_exp:
        # now_level = now_level+1
        # now_exp = now_exp-need_exp
        # need_exp = (now_level+1)*100 
        # if now_level>=120:
            # level_flag = 1
            # last_exp = now_exp
            # now_exp = 0
            # break
    # if level_flag == 1:
        # CE._add_card_exp(gid, uid, cid, now_level, now_exp)
        # CE._add_exp_chizi(gid, uid, last_exp)
        # msg = f"\n目前等级为{now_level}，由于超出等级上限，{last_exp}点经验加入经验池"
        # return [1,last_exp,msg]
    # else:
        # CE._add_card_exp(gid, uid, cid, now_level, now_exp)
        # msg = f"\n目前等级为{now_level}"
        # return [0,now_level,msg]

#撤回消息
# async def del_msg_run(bot, ev, msg_id, sleeptime):
    # self_id=ev.self_id
    # await bot.send(ev,f"{self_id}开始撤回消息{msg_id}")
    # bot = nonebot.get_bot()
    # await bot.delete_msg(self_id,msg_id)

#将角色以角色编号的形式分配到赛道上，返回一个赛道的列表。
def chara_select():
    l = range(1,TOTAL_NUMBER+1)
    select_list = random.sample(l,5)
    return select_list
#取得指定角色编号的赛道号,输入分配好的赛道和指定角色编号
def get_chara_id(list,id):
    raceid= list.index(id)+1
    return raceid
       
#输入赛道列表和自己的赛道，选出自己外最快的赛道
def select_fast(position,id):
    list1 = copy.deepcopy(position) 
    list1[id-1] = 999
    fast = list1.index(min(list1))
    return fast+1

#输入赛道列表和自己的赛道，选出自己外最慢的赛道。 
def select_last(position,id):
    list1 = copy.deepcopy(position)
    list1[id-1] = 0
    last = list1.index(max(list1))
    return last+1    
    
#输入赛道列表，自己的赛道和数字n，选出自己外第n快的赛道。     
def select_number(position,id,n):
    lis = copy.deepcopy(position)
    lis[id-1] = 999
    max_NUMBER = heapq.nsmallest(n, lis) 
    max_index = []
    for t in max_NUMBER:
        index = lis.index(t)
        max_index.append(index)
        lis[index] = 0
    nfast = max_index[n-1]
    return nfast+1

#输入自己的赛道号，选出自己外的随机1个赛道，返回一个赛道编号   
def select_random(id):
    l1 = range(1,NUMBER+1)
    list(l1).remove(id)
    select_id = random.choice(l1)
    return select_id

#输入自己的赛道号和数字n，选出自己外的随机n个赛道，返回一个赛道号的列表   
def nselect_random(id,n):
    l1 = range(1,NUMBER+1)
    list(l1).remove(id)
    select_list = random.sample(l1,n)
    return select_list
    
#选择除自己外的全部对象，返回赛道号的列表
def select_all(id):
    l1 = list(range(1,NUMBER+1))
    l1.remove(id)
    return l1

#选择比自己快的全部对象，返回赛道号的列表
def select_fast_all(id,position):
    l1 = list(range(1,NUMBER+1))
    l1.remove(id)
    for rid in l1:
        if position[rid-1] > position[id-1]:
            l1.remove(rid)
    return l1
    
#选择和自己同一位置的全部对象，返回赛道号的列表
def select_xt_all(id,position):
    l1 = list(range(1,NUMBER+1))
    l1.remove(id)
    for rid in l1:
        if position[rid-1] != position[id-1]:
            l1.remove(rid)
    return l1
    
def search_kokoro(charalist):
    if 10 in charalist:
        return charalist.index(10)+1
    
    else:
        return None


def create_gif(image_list, gid, duration=0.35):
    fourcc = cv2.VideoWriter_fourcc('X','V','I','D')
    GIF_PATH = os.path.join(FILE_PATH,'gifs')
    video_name = f'{gid}_run.avi'
    videos_name = f'{gid}_1_run.avi'
    videos = os.path.join(GIF_PATH,video_name)
    videos_a = os.path.join(GIF_PATH,videos_name)
    cap_fps = 2
    size = (800, 645)
    video = cv2.VideoWriter(videos,fourcc, cap_fps, size)
    for filename in image_list:
        image_name = os.path.join(GIF_PATH,filename)
        img = cv2.imread(image_name)
        video.write(img)
    video.release()
    
    # audios = os.path.join(GIF_PATH,'bgm.mp3')
    
    # #需添加背景音乐的视频
    # video_clip = VideoFileClip(videos)
    # #提取视频对应的音频，并调节音量
    # #video_audio_clip = video_clip.audio.volumex(0.8)
    # #背景音乐
    # audio_clip = AudioFileClip(audios).volumex(0.8)
    # #设置背景音乐循环，时间与视频时间一致
    # audio = afx.audio_loop( audio_clip, duration=video_clip.duration)
    # #视频声音和背景音乐，音频叠加
    # #audio_clip_add = CompositeAudioClip([video_audio_clip,audio])

    # #视频写入背景音
    # final_video = video_clip.set_audio(audio)

    # #将处理完成的视频保存
    # final_video.write_videofile(videos_a)


    gif_send = f'[CQ:video,file=file:///{os.path.abspath(videos)}]'

    return gif_send

def save_base64_img(sss,name):
    GIF_PATH = os.path.join(FILE_PATH,'gifs')
    image_name = os.path.join(GIF_PATH,name)
    imagedata = base64.b64decode(sss)
    file = open(image_name,"wb")
    file.write(imagedata)
    file.close()


#对单一对象的基本技能：前进，后退，沉默，暂停，必放ub
def forward(id,step,position):
    fid = int(id)
    position[fid-1] = position[fid-1] - step
    position[fid-1] = max (1,position[fid-1])
    return
    
def backward(id,step,position,wudi):
    if wudi[id-1] == 0:
        position[id-1] = position[id-1] + step
        position[id-1] = min (ROADLENGTH,position[id-1])
    return  

def gengsui(id,rid,position):
    position[id-1] = position[rid-1]
    return

def give_silence(id,num,silence):
    silence[id-1] += num
    return   

def give_shiting(id,num,shiting):
    shiting[id-1] += num
    return  

def give_fanxiang(id,num,fanxiang):
    fanxiang[id-1] += num
    return 

def give_pause(id,num,pause):
    pause[id-1] += num
    return
    
def give_wudi(id,num,wudi):
    wudi[id-1] += num
    return

def give_ub(id,num,ub):
    ub[id-1] += num
    return
    
def give_dosid(id,sid,dosid):
    dosid[id-1] = sid
    return

def kaojin(rid,id,step,position,wudi):
    if wudi[rid-1] == 0:
        if position[rid-1] < position[id-1]:
            if position[id-1] - position[rid-1] < step:
                position[rid-1] = position[id-1]
            else:
                position[rid-1] = position[rid-1] + step
                position[rid-1] = min (ROADLENGTH,position[rid-1])
        elif position[rid-1] > position[id-1]:
            if position[rid-1] - position[id-1] < step:
                position[rid-1] = position[id-1]
            else:
                position[rid-1] = position[rid-1] - step
                position[rid-1] = max (1,position[rid-1])
    return

def yuanli(rid,id,step,position,wudi):
    if wudi[rid-1] == 0:
        if position[rid-1] < position[id-1]:
            if position[id-1] - position[rid-1] < step:
                position[rid-1] = position[id-1]
            else:
                position[rid-1] = position[rid-1] - step
                position[rid-1] = max (1,position[rid-1])
        elif position[rid-1] > position[id-1]:
            if position[rid-1] - position[id-1] < step:
                position[rid-1] = position[id-1]
            else:
                position[rid-1] = position[rid-1] + step
                position[rid-1] = min (ROADLENGTH,position[rid-1])
        else:
            position[rid-1] = position[rid-1] + step
            position[rid-1] = min (ROADLENGTH,position[rid-1])
    return

def change_position(id,rid,position,wudi):
    if wudi[rid-1] == 0:
        position[id-1],position[rid-1] = position[rid-1],position[id-1]
    else:
        position[id-1] = position[rid-1]
    return 

#用于技能参数增加
def add(a,b):
    return a+b

   



#对列表多对象的基本技能

def n_forward(list,step,position):
    for id in list:
        position[id-1] = position[id-1] - step
        position[id-1] = max (1,position[id-1])
    return

def n_gengsui(list,rid,position):
    for id in list:
        position[id-1] = position[rid-1]
    return

def n_give_fanxiang(list,num,fanxiang):
    for id in list:
        fanxiang[id-1] += num
    return 

def n_backward_r(list,start,step,position,wudi):
    text = ''
    for id in list:
        if wudi[id-1] == 0:
            tostep = int(math.floor( random.uniform(start,step) ))
            text = text + f"{id}号选手后退{tostep}步。"
            position[id-1] = position[id-1] + tostep
            position[id-1] = min (ROADLENGTH,position[id-1])
    return text

def n_kaojin(list,id,step,position,wudi):
    for rid in list:
        if wudi[rid-1] == 0:
            if position[rid-1] < position[id-1]:
                if position[id-1] - position[rid-1] < step:
                    position[rid-1] = position[id-1]
                else:
                    position[rid-1] = position[rid-1] + step
                    position[rid-1] = min (ROADLENGTH,position[rid-1])
            elif position[rid-1] > position[id-1]:
                if position[rid-1] - position[id-1] < step:
                    position[rid-1] = position[id-1]
                else:
                    position[rid-1] = position[rid-1] - step
                    position[rid-1] = max (1,position[rid-1])
    return

def n_yuanli(list,id,step,position,wudi):
    for rid in list:
        if wudi[rid-1] == 0:
            if position[rid-1] < position[id-1]:
                if position[id-1] - position[rid-1] < step:
                    position[rid-1] = position[id-1]
                else:
                    position[rid-1] = position[rid-1] - step
                    position[rid-1] = max (1,position[rid-1])
            elif position[rid-1] > position[id-1]:
                if position[rid-1] - position[id-1] < step:
                    position[rid-1] = position[id-1]
                else:
                    position[rid-1] = position[rid-1] + step
                    position[rid-1] = min (ROADLENGTH,position[rid-1])
            else:
                position[rid-1] = position[rid-1] + step
                position[rid-1] = min (ROADLENGTH,position[rid-1])
    return

def n_give_shiting(list,num,shiting):
    for id in list:
        shiting[id-1] += num
    return   

def n_run_r(list,start,step,position,wudi):
    text = ''
    for id in list:
        text = text + f"{id}号选手"
        go_num =  int(math.floor( random.uniform(1,100) ))
        if go_num>50:
            go_flag = 1
            text = text + "前进"
        else:
            if wudi[id-1] == 0:
                go_flag = -1
                text = text + "后退"
        tostep = int(math.floor( random.uniform(start,step) ))
        text = text + f"{tostep}步。"
        if go_flag == 1:
            position[id-1] = position[id-1] - tostep
            position[id-1] = max (1,position[id-1])
        else:
            if wudi[id-1] == 0:
                position[id-1] = position[id-1] + tostep
                position[id-1] = min (ROADLENGTH,position[id-1])
    return  text

def prob_for_back(list,id,step,tostep,position,wudi):
    text = ''
    if list[0]:
        text = text + "\n该位置已有人"
        for rid in list:
            if wudi[rid-1] == 0:
                text = text + f"{rid}号选手后退{step}步"
                position[rid-1] = position[rid-1] + step
                position[rid-1] = min (ROADLENGTH,position[rid-1])
            else:
                text = text + f"{rid}号选手霸体免疫"
    else:
        position[id-1] = position[id-1] - tostep
        position[id-1] = max (1,position[id-1])
        text = text + "路径上无人再前进1格"
    return  text

def n_backward(list,step,position,wudi):
    for id in list:
        if wudi[id-1]==0:
            position[id-1] = position[id-1] + step
            position[id-1] = min (ROADLENGTH,position[id-1])
    return  

def n_give_silence(list,num,silence):
    for id in list:
        silence[id-1] += num
    return   

def n_give_prob_pause(list_fast,list_all,num1,num2,pause):
    text = ""
    if list_fast[0]:
        list = list_fast
        num = num1
        text = f"使比自己快的选手暂停{num1}回合"
    else:
        list = list_all
        num = num2
        text = f"使除自己外全员暂停{num2}回合"
    n_give_pause(list,num,pause)
    return text

def n_give_prob_silence(list_fast,list_all,num1,num2,silence):
    text = ""
    if list_fast[0]:
        list = list_fast
        num = num1
        text = f"使比自己快的选手沉默{num1}回合"
    else:
        list = list_all
        num = num2
        text = f"使除自己外全员沉默{num2}回合"
    n_give_silence(list,num,silence)
    return text

def n_give_wudi(list,num,wudi):
    for id in list:
        wudi[id-1] += num
    return 

def n_give_pause(list,num,pause):
    for id in list:
        pause[id-1] += num
    return

def n_give_ub(list,num,ub):
    for id in list:
        ub[id-1] += num
    return

#概率触发的基本技能
def prob_forward(prob,id,step,position):
    r=random.random()
    if r < prob:
        forward(id,step,position)
        return 1
    else :
        return 0

def prob_gengsui(prob,id,rid,position):
    r=random.random()
    if r < prob:
        position[id-1] = position[rid-1]
        return 1
    else :
        return 0
        
def prob_backward(prob,id,step,position):
    r=random.random()
    if r < prob:
        backward(id,step,position)
        return 1
    else :
        return 0        
        
def prob_give_pause(prob,id,num,pause):
    r=random.random()
    if r < prob:
        give_pause(id,num,pause)
        return 1
    else :
        return 0

def prob_give_silence(prob,id,num,silence):
    r=random.random()
    if r < prob:
        give_silence(id,num,silence)
        return 1
    else :
        return 0

#根据概率触发技能的返回，判断是否增加文本，成功返回成功文本，失败返回失败文本
def prob_text(is_prob,text1,text2):
    if is_prob == 1:
        addtion_text = text1
    else:
        addtion_text = text2
    return addtion_text

#按概率表选择一个技能编号
def skill_select(cid):
    c = runchara.Run_chara(str(cid))
    skillnum_ = ['0','1', '2', '3', '4']
    #概率列表,读json里的概率，被注释掉的为老版本固定概率
    r_ = c.getskill_prob_list()
   #r_ = [0.7, 0.1, 0.1, 0.08, 0.02]
    sum_ = 0
    ran = random.random()
    for num, r in zip(skillnum_, r_):
        sum_ += r
        if ran < sum_ :break
    return int (num)

#加载指定角色的指定技能，返回角色名，技能文本和技能效果
def skill_load(cid,sid):
    c = runchara.Run_chara(str(cid))
    name = c.getname()
    if sid == 0:
        return name,"none","null"
    else :
        skill_text = c.getskill(sid)["skill_text"]
        skill_effect = c.getskill(sid)["skill_effect"]
        return name,skill_text,skill_effect
    
    
#指定赛道的角色释放技能，输入分配好的赛道和赛道编号
def skill_unit(Race_list,rid,position,silence,pause,ub,wudi,shiting,fanxiang,dosid,gid):
    #检查是否被沉默
    cid = Race_list[rid-1]
    if dosid[rid-1] > 0:
        sid = dosid[rid-1]
    else:
        sid = skill_select(cid)
    if ub[rid-1] > 1:
        ub[rid-1]-= 1
    if ub[rid-1] == 1:
        sid = 3
        ub[rid-1]-= 1
        
    skill = skill_load(cid,sid)
    skillmsg = skill[0]
    skillmsg += ":"
    if shiting[rid-1] > 0:
        skillmsg += "本回合停止中"
        shiting[rid-1] -= 1
        return skillmsg
    if silence[rid-1] > 0:
        if wudi[rid-1] == 0:
            skillmsg += "本回合被沉默"
            give_dosid(rid,0,dosid)
            silence[rid-1] -= 1
            return skillmsg
    if wudi[rid-1] > 0:
        skillmsg += "[霸体]"
        wudi[rid-1] -= 1
    skillmsg += skill[1]
    list = Race_list
    id = rid
    position = position
    silence = silence
    pause = pause
    ub = ub
    dosid = dosid
    fanxiang = fanxiang
    wudi = wudi
    shiting = shiting
    kan_num = numrecord.get_kan_num(gid)
    kokoro_num = numrecord.get_kokoro_num(gid)
    if skill[2]== "null":
        return skillmsg
    loc = locals()    
    addtion_text = ''
    exec(skill[2])
    if 'text'in loc.keys():
        addtion_text = loc['text']
    if 'kan_num1'in loc.keys():
        numrecord.add_kan_num(gid,loc['kan_num1'])         
    skillmsg += addtion_text
    
    return skillmsg
    
#每个赛道的角色轮流释放技能    
def skill_race(Race_list,position,silence,pause,ub,wudi,shiting,fanxiang,dosid,gid,runimg_list,i,runtype):
    skillmsg = "技能发动阶段:\n"
    for rid in range(1,6):
        position_old = []
        position_old = copy.deepcopy(position)
        skillmsg += skill_unit(Race_list,rid,position,silence,pause,ub,wudi,shiting,fanxiang,dosid,gid)
        runimg_list = print_race(Race_list,position_old,position,skillmsg,gid,runimg_list,i,runtype,rid)
        if rid !=5:
            skillmsg += "\n"
    return runimg_list    
        
   
    
#初始状态相关函数    
def position_init(position):
    for i in range (0,NUMBER):
        position[i] = ROADLENGTH
    return
    
def silence_init(silence):
    for i in range (0,NUMBER):
        silence[i] = 0
    return
    
def pause_init(pause):
    for i in range (0,NUMBER):
        pause[i] = 0
    return    

def wudi_init(wudi):
    for i in range (0,NUMBER):
        wudi[i] = 0
    return

def shiting_init(shiting):
    for i in range (0,NUMBER):
        shiting[i] = 0
    return

def ub_init(ub):
    for i in range (0,NUMBER):
        ub[i] = 0
    return   

def fanxiang_init(fanxiang):
    for i in range (0,NUMBER):
        fanxiang[i] = 0
    return   

def dosid_init(dosid):
    for i in range (0,NUMBER):
        dosid[i] = 0
    return     

#赛道初始化
def race_init(position,silence,pause,ub,wudi,shiting,fanxiang,dosid):
    position_init(position)
    silence_init(silence)
    pause_init(pause)
    ub_init(ub)
    wudi_init(wudi)
    shiting_init(shiting)
    fanxiang_init(fanxiang)
    dosid_init(dosid)
    return
    
#一个角色跑步 检查是否暂停
def one_unit_run(id,pause,wudi,shiting,fanxiang,position,Race_list):
    text = ""
    if  pause[id-1]  == 0:
        if shiting[id-1] == 0:
            cid = Race_list[id-1]
            c = runchara.Run_chara(str(cid))
            speedlist = c.getspeed()
            step = random.choice(speedlist)
            if fanxiang[id-1]>0:
                backward(id,step,position,wudi)
                fanxiang[id-1]-=1
                runtype = "后退"
            else:
                forward(id,step,position)
                runtype = "前进"
            text = f"{id}号选手{runtype}{step}步"
        else:
            shiting[id-1]-=1
            text = f"{id}号选手停止中"
    else:
        if wudi[id-1] > 0:
            cid = Race_list[id-1]
            c = runchara.Run_chara(str(cid))        
            speedlist = c.getspeed()
            step = random.choice(speedlist)
            if fanxiang[id-1]>0:
                fanxiang[id-1]-=1
            forward(id,step,position)
            text = f"[霸体]{id}号选手前进{step}步"
        pause[id-1]-=1
        text = f"{id}号选手暂停中"
    return text
           
#一轮跑步，每个角色跑一次    
def one_turn_run(pause,wudi,shiting,fanxiang,position,Race_list):
    msg = ''
    for id in range(1,6):
        msg += one_unit_run(id,pause,wudi,shiting,fanxiang,position,Race_list)
        msg += '\n'
        
    return msg

#打印当前跑步状态
def print_race(Race_list,position_old,position,msg,gid,runimg_list,i,runtype,rid):
    
    ICON_PATH = os.path.join(FILE_PATH,'icon')
    FONTS_PATH = os.path.join(FILE_PATH,'fonts')
    FONTS = os.path.join(FONTS_PATH,'msyh.ttf')
    font = ImageFont.truetype(FONTS, 14)
    for shul in range(1,2):
        im = Image.new("RGB", (800, 645), (255, 255, 255))
        base_img = os.path.join(FILE_PATH, "run_bg.jpg")
        dtimg = Image.open(base_img)
        dtbox = (0, 0)
        im.paste(dtimg, dtbox)
        
        dr = ImageDraw.Draw(im)
        for id in range(1,6):
            cid = Race_list[id-1]
            c = runchara.Run_chara(str(cid))
            icon = c.geticon()
            image = c.getimg()
            n = position_old[id-1]
            weiyi = (position_old[id-1]-position[id-1])*(50*shul)
            image_path = os.path.join(ICON_PATH,image)
            img = Image.open(image_path).convert('RGBA')
            size = img.size
            sf_weight = math.ceil(size[0]/(size[1]/65))
            img = img.resize((sf_weight, 65))
            top_height = 160+(id-1)*60-10
            left = 25 + (n-1)*50 - weiyi
            box = (left, top_height)
            im.paste(img, box, mask=img.split()[3])
        dr.text((85, 470), msg, font=font, fill="#06a6d8")
        bio  = BytesIO()
        im.save(bio, format='PNG')
        
        base64_img = base64.b64encode(bio.getvalue()).decode()
        img_name = f'{gid}_{i}_{runtype}_{rid}_{shul}.jpg'
        save_base64_img(base64_img,img_name)
        runimg_list.append(img_name)
    return runimg_list
#检查比赛结束用，要考虑到同时冲线
def check_game(position,winner):
    xuhao = 1
    is_win = 0
    xuhao=xuhao+len(winner)
    for id in range(1,6):
        mc_flag=0
        mingcixx=[]
        if position[id-1] == 1:
            for win in winner:
                if id==win[1]:
                    mc_flag=1
            if mc_flag==0:
                mingcixx=[xuhao,id]
                winner.append(mingcixx)
                if len(winner)>=3:
                    is_win = 1
    return is_win,winner  



def introduce_race(Race_list):
    msg = ''
    ICON_PATH = os.path.join(FILE_PATH,'icon')
    for id in range(1,6):
        msg += f'{id}号：'
        cid = Race_list[id-1]
        c = runchara.Run_chara(str(cid))
        icon = c.geticon()
        name = c.getname()
        image = c.getimg()
        image_path = os.path.join(ICON_PATH,image)
        img = Image.open(image_path).convert('RGBA')
        size = img.size
        sf_weight = math.ceil(size[0]/(size[1]/65))
        img = img.resize((sf_weight, 65))
        bio = BytesIO()
        img.save(bio, format='PNG')
        base64_str = 'base64://' + base64.b64encode(bio.getvalue()).decode()
        mes = f"[CQ:image,file={base64_str}]"
        msg += f'{mes}{name}'
        msg += "\n" 
    msg += f"所有人请在{SUPPORT_TIME}秒内选择支持的选手。格式如下：\n1/2/3/4/5号xx金币\n如果金币为0，可以发送：\n领赛跑金币"    
    return msg    
        
@sv.on_prefix(('测试赛跑', '赛跑开始'))
async def Racetest(bot, ev: CQEvent):
    #if not priv.check_priv(ev, priv.ADMIN):
    #    await bot.finish(ev, '只有群管理才能开启赛跑', at_sender=True)
    if running_judger.get_on_off_status(ev.group_id):
        await bot.send(ev, "此轮赛跑还没结束，请勿重复使用指令。")
        return
    runimg_list = []
    running_judger.turn_on(ev.group_id)
    gid = ev.group_id
    #用于记录各赛道上角色位置，第i号角色记录在position[i-1]上
    position = [ROADLENGTH for x in range(0,NUMBER)]
    #同理，记录沉默，暂停，以及必放ub标记情况
    silence = [0 for x in range(0,NUMBER)]
    pause = [0 for x in range(0,NUMBER)]
    ub = [0 for x in range(0,NUMBER)]
    wudi = [0 for x in range(0,NUMBER)]
    shiting = [0 for x in range(0,NUMBER)]
    fanxiang = [0 for x in range(0,NUMBER)]
    dosid = [0 for x in range(0,NUMBER)]
    numrecord.init_num(gid)
    Race_list = chara_select()
    msg = '幻想乡赛跑即将开始！\n下面为您介绍参赛选手：'
    ret = await bot.send(ev, msg)

    await asyncio.sleep(ONE_TURN_TIME)
    #介绍选手，开始支持环节
    running_judger.xiazhu_on(ev.group_id)
    msg = introduce_race(Race_list)
    await bot.send(ev, msg)

    position_old = []
    race_init(position,silence,pause,ub,wudi,shiting,fanxiang,dosid)
    position_old = copy.deepcopy(position)
    msg = '运动员们已经就绪！\n'
    runimg_list = print_race(Race_list,position_old,position,msg,gid,runimg_list,'0','0','0')

    gameend = 0
    i = 1
    winner = []
    start = time.time()
    
    while gameend == 0:
        
        runmsg = f'第{i}轮跑步:\n'
        position_old = copy.deepcopy(position)
        runmsg += one_turn_run(pause,wudi,shiting,fanxiang,position,Race_list)
        runimg_list = print_race(Race_list,position_old,position,runmsg,gid,runimg_list,i,'1','0')

        
        check = check_game(position,winner)
        if check[0]!=0:
            break
            
        position_old = copy.deepcopy(position)
        #skillmsg = "技能发动阶段:\n"
        runimg_list = skill_race(Race_list,position,silence,pause,ub,wudi,shiting,fanxiang,dosid,gid,runimg_list,i,'2')

        i+=1
        check = check_game(position,check[1])
        gameend = check[0]
    
    
    
    while time.time() - start < SUPPORT_TIME:
        await asyncio.sleep(.1)
        
    await asyncio.sleep(10)
    gif_name = create_gif(runimg_list, gid, 1.5)
    #支持环节结束
    msg = '支持环节结束，下面赛跑正式开始。'
    await bot.send(ev, msg)     
    
    
    await bot.send(ev, gif_name)
    
    await asyncio.sleep(10)
    running_judger.xiazhu_off(ev.group_id)
    
    winner = check[1]
    winshuchu=''
    winmsg1=''
    winmsg2=''
    winmsg3=''
    for win in winner:
        cid = Race_list[win[1]-1]
        c = runchara.Run_chara(str(cid))
        name = c.getname()
        if win[0]==1:
            winmsg1 += str(win[1])+f'号选手({name})\n'
        if win[0]==2:
            winmsg2 += str(win[1])+f'号选手({name})\n'
        # if win[0]==3:
            # winmsg3 += str(win[1])+f'号选手({name})\n'
    if winmsg1:
        winshuchu += "第一名为:\n"+winmsg1
    if winmsg2:
        winshuchu += "第二名为:\n"+winmsg2
    # if winmsg3:
        # winshuchu += "第三名为:\n"+winmsg3
    msg = f'胜利者:\n{winshuchu}'
    score_counter = ScoreCounter()
    await bot.send(ev, msg)
    gid = ev.group_id
    support = running_judger.get_support(gid)
    winuid = []
    shengwangmsg = ''
    supportmsg = '金币结算:\n'
    bd_msg=''
    if support!=0:
        CE = CECounter()
        for uid in support:
            support_id = support[uid][0]
            support_score = support[uid][1]
            jl_mingci=0
            for win in winner:
                if win[1]==support_id:
                    jl_mingci=win[0]
                    break
            if jl_mingci==1:
                winuid.append(uid)
                winscore = support_score*1.5
                #addscore = winscore+support_score
                score_counter._add_score(gid, uid ,winscore)
                # score_counter._add_prestige(gid,uid,200)
                # shengwangmsg += f'[CQ:at,qq={uid}]+200声望\n'  
                supportmsg += f'[CQ:at,qq={uid}]+{winscore}金币\n'
                
                # bangdinwin = CE._get_guaji(gid, uid)
                # #判断决斗胜利者是否有绑定角色,有则增加经验值
                # if bangdinwin:
                    # bdname = _pcr_data.CHARA_NAME[bangdinwin][0]
                    # card_level=add_exp(gid,uid,bangdinwin,300)
                    # bd_msg = bd_msg + f"[CQ:at,qq={uid}]您绑定的女友{bdname}获得了3000点经验，{card_level[2]}\n"
            elif jl_mingci==2:
                winuid.append(uid)
                winscore = support_score*1
                #addscore = winscore+support_score
                score_counter._add_score(gid, uid ,winscore)
                supportmsg += f'[CQ:at,qq={uid}]+{winscore}金币\n'   
                # bangdinwin = CE._get_guaji(gid, uid)
                # #判断决斗胜利者是否有绑定角色,有则增加经验值
                # if bangdinwin:
                    # bdname = _pcr_data.CHARA_NAME[bangdinwin][0]
                    # card_level=add_exp(gid,uid,bangdinwin,150)
                    # bd_msg = bd_msg + f"[CQ:at,qq={uid}]您绑定的女友{bdname}获得了1500点经验，{card_level[2]}\n"
            # elif jl_mingci==3:
                # winuid.append(uid)
                # winscore = support_score*0.5
                # #addscore = winscore+support_score
                # score_counter._add_score(gid, uid ,winscore)
                # supportmsg += f'[CQ:at,qq={uid}]+{winscore}金币\n'   
                # bangdinwin = CE._get_guaji(gid, uid)
                # #判断决斗胜利者是否有绑定角色,有则增加经验值
                # if bangdinwin:
                    # bdname = _pcr_data.CHARA_NAME[bangdinwin][0]
                    # card_level=add_exp(gid,uid,bangdinwin,100)
                    # bd_msg = bd_msg + f"[CQ:at,qq={uid}]您绑定的女友{bdname}获得了1000点经验，{card_level[2]}\n"
            else:
                score_counter._reduce_score(gid, uid ,support_score)
                supportmsg += f'[CQ:at,qq={uid}]-{support_score}金币\n'
    # await asyncio.sleep(2)
    # if shengwangmsg == '':
        # shengwangmsg='无\n'
    # supportmsg += f'声望结算：\n{shengwangmsg}(猜对第一名结算声望加200点)'
    # await bot.send(ev, supportmsg)
    # if bd_msg:
        # await asyncio.sleep(1)
        # await bot.send(ev, f"绑定女友经验结算：\n{bd_msg}")
    running_judger.set_support(ev.group_id) 
    running_judger.turn_off(ev.group_id)
 
@sv.on_rex(r'^(\d+)号(\d+)(金币|分)$') 
async def on_input_score(bot, ev: CQEvent):
    try:
        if running_judger.get_xiazhu_on_off_status(ev.group_id):
            gid = ev.group_id
            uid = ev.user_id
            
            match = ev['match']
            select_id = int(match.group(1))
            input_score = int(match.group(2))
            score_counter = ScoreCounter()
            #若下注该群下注字典不存在则创建
            if running_judger.get_support(gid) == 0:
                running_judger.set_support(gid)
            support = running_judger.get_support(gid)
            #检查是否重复下注
            if uid in support:
                msg = '您已经支持过了。'
                await bot.send(ev, msg, at_sender=True)
                return
            #检查金币是否足够下注
            if score_counter._judge_score(gid, uid ,input_score) == 0:
                msg = '您的金币不足。'
                await bot.send(ev, msg, at_sender=True)
                return
            else :
                running_judger.add_support(gid,uid,select_id,input_score)
                #score_counter._reduce_score(gid, uid ,input_score)
                msg = f'支持{select_id}号成功。'
                await bot.send(ev, msg, at_sender=True)                
    except Exception as e:
        await bot.send(ev, '错误:\n' + str(e))            
            
                
                
@sv.on_prefix('领赛跑金币')
async def add_score(bot, ev: CQEvent):
    try:
        score_counter = ScoreCounter()
        gid = ev.group_id
        uid = ev.user_id
        
        current_score = score_counter._get_score(gid, uid)
        if current_score == 0:
            score_counter._add_score(gid, uid ,50)
            msg = '您已领取50金币'
            await bot.send(ev, msg, at_sender=True)
            return
        else:     
            msg = '金币为0才能领取哦。'
            await bot.send(ev, msg, at_sender=True)
            return
    except Exception as e:
        await bot.send(ev, '错误:\n' + str(e))         
@sv.on_prefix('查赛跑金币')
async def get_score(bot, ev: CQEvent):
    try:
        score_counter = ScoreCounter()
        gid = ev.group_id
        uid = ev.user_id
        
        current_score = score_counter._get_score(gid, uid)
        msg = f'您的金币为{current_score}'
        await bot.send(ev, msg, at_sender=True)
        return
    except Exception as e:
        await bot.send(ev, '错误:\n' + str(e)) 
        
async def get_user_card_dict(bot, group_id):
    mlist = await bot.get_group_member_list(group_id=group_id)
    d = {}
    for m in mlist:
        d[m['user_id']] = m['card'] if m['card']!='' else m['nickname']
    return d        
@sv.on_fullmatch(('赛跑排行榜', '赛跑群排行'))
async def Race_ranking(bot, ev: CQEvent):
    try:
        user_card_dict = await get_user_card_dict(bot, ev.group_id)
        score_dict = {}
        score_counter = ScoreCounter()
        gid = ev.group_id
        for uid in user_card_dict.keys():
            if uid != ev.self_id:
                score_dict[user_card_dict[uid]] = score_counter._get_score(gid, uid)
        group_ranking = sorted(score_dict.items(), key = lambda x:x[1], reverse = True)
        msg = '此群赛跑金币排行为:\n'
        for i in range(min(len(group_ranking), 10)):
            if group_ranking[i][1] != 0:
                msg += f'第{i+1}名: {group_ranking[i][0]}, 金币: {group_ranking[i][1]}分\n'
        await bot.send(ev, msg.strip())
    except Exception as e:
        await bot.send(ev, '错误:\n' + str(e))        
    
@sv.on_fullmatch(('重置赛跑'))
async def run_congzhi(bot, ev: CQEvent):
    try:
        running_judger.turn_off(ev.group_id)
        running_judger.xiazhu_off(ev.group_id)
        running_judger.set_support(ev.group_id) 
        await bot.send(ev, "赛跑重置成功")
    except Exception as e:
        await bot.send(ev, '错误:\n' + str(e)) 
    
        
        
        
        
   
    
    
    
    
    
    
    
    
    





    
