import numpy as np
from copy import copy
class RGV(object):
    def __init__(self, pos, group, type, groups_para):
        self.pos = pos      # RGV位置
        self.group = group  # {1, 2, 3}组
        self.type = type    # 1:一道工序; 2:两道工序
        self.status = 0     # 0:停止等待; 1:移动;  2:上下料; 3:清洗作业
        self.hand_1 = [0,-1]     # 机械手爪_1 手持物：0，空；1，生料；2，一次加工后；3，熟料 + 编号
        self.hand_2 = [0,-1]     # 机械手爪_2 手持物：0，空；1，生料；2，一次加工后；3，熟料 + 编号
        self.dir = -1       # 移动方向 -1代表向左，1代表向右
        self.distance = 0   # 移动距离
        self.num_sever_cnc = 0  # rgv此刻服务的cnc编号，0代表无服务对象。
        self.pos_sever_cnc = -1 # rgv此刻服务的cnc位置，-1代表无服务对象。
        self.group = group  # {1, 2, 3}组
        self.time_mv1 = groups_para[self.group-1][0]  # RGV移动1个单位所需时间
        self.time_mv2 = groups_para[self.group-1][1]  # RGV移动2个单位所需时间
        self.time_mv3 = groups_para[self.group-1][2]  # RGV移动3个单位所需时间
        self.time_mv_ls = [self.time_mv1, self.time_mv2, self.time_mv3]
        
        self.time_odd = groups_para[self.group-1][6] # RGV为CNC1#，3#，5#，7#一次上下料所需时间
        self.time_eve = groups_para[self.group-1][7] # RGV为CNC2#，4#，6#，8#一次上下料所需时间
        self.time_wash = groups_para[self.group-1][8]  # RGV完成一个物料的清洗作业所需时间
        self.task_time = 0  # 完成上一个任务的剩余时间，为0表示rgv处于闲置状态

        self.idle_time = 0
        self.move_time = 0
        self.updown_time = 0
        self.wash_time = 0
        self.avg_distance = 0

        self.cnc_mean_wait_time = 0
        self.num_result = 0

        self.sum_move_distance = 0
        self.max_dist = 100000

        self.cnt_container = 0 # 原料计数器
        self.result_ls_task1 = [ [0,0,0,0] for i in range(2000) ]
        self.result_ls_task2 = [ [0,0,0,0,0,0,0] for i in range(2000) ]
    
    def change_hand_status(self, k, cnc_ls):
        cnc = cnc_ls[k-1]
        up_container = None
        down_container = None
        # 一道工序
        if cnc.type == 0:
            if cnc.container[0] != 0:
                self.cnt_container += 1
                self.hand_1 = [1 ,self.cnt_container]   # 用hand_1去抓原料
                self.hand_2 = copy(cnc.container)        # 用hand_2去cnc上取料
                cnc.container = copy(self.hand_1)        # 用hand_1将原料放置到cnc上
                self.hand_1 = copy(self.hand_2)                   # 清空hand_1
            else:
                self.cnt_container += 1
                self.hand_1 = [1, self.cnt_container]   # 用hand_1去抓原料
                cnc.container = copy(self.hand_1)
                self.hand_1 = [0, -1]                   # 清空hand_1

        # 两道工序之一
        if cnc.type == 1:
            # cnc上面不是空的
            if cnc.container[0] != 0:
                self.cnt_container += 1
                self.hand_1 = [1 ,self.cnt_container]   # 用hand_1去抓原料
                self.hand_2 = copy(cnc.container)        # 用hand_2去cnc上取料
                cnc.container = copy(self.hand_1)        # 用hand_1将原料放置到cnc上
                self.hand_1 = copy(self.hand_2)               # 取下来的原料放到hand_1上
                self.hand_2 = [0, -1]                   # 清空hand_2
            # cnc上面是空的
            else:
                self.cnt_container += 1
                self.hand_1 = [1, self.cnt_container]   # 用hand_1去抓原料
                cnc.container = copy(self.hand_1)             # 用hand_1将原料放置到cnc上
                self.hand_1 = [0, -1]                   # 清空hand_1
        if cnc.type == 2:
            # cnc上面不是空的
            if cnc.container[0] != 0:
                self.hand_2 = copy(cnc.container)    # 取下熟料
                cnc.container = copy(self.hand_1)    # 在cnc上放上一道加工后的料
                self.hand_1 = copy(self.hand_2)      # 取下来的熟料放到hand_1上
                self.hand_2 = [0, -1]          # 清空hand_2
            # cnc上面是空的
            else:
                cnc.container = copy(self.hand_1)    # 在cnc上放上一道加工后的料
                self.hand_1 = [0, -1]          # 清空hand_1

        up_container = copy(cnc.container)
        down_container = copy(self.hand_1)

        assert up_container[1] != down_container[1]
        return cnc.get_num(), up_container, down_container

    def release_hand(self):
        if self.hand_1[0] == 3 or self.hand_2[0] == 3:
            self.hand_1 = [0, -1]
            self.hand_2 = [0, -1]
    
    def get_hand_1(self):
        return self.hand_1

    def get_hand_2(self):
        return self.hand_2

    def update_status_move(self, wait_queue_ls, wait_set_ls, cnc_ls, mode, time):
        # 选择移动目标cnc
        k = self.select_cnc(wait_queue_ls, wait_set_ls, cnc_ls, mode)
        if k == -1:
            return k
        
        self.num_sever_cnc = k

        # 计算next_cnc的位置
        self.pos_sever_cnc = (self.num_sever_cnc - 1) // 2
        # 计算移动距离
        self.distance = abs(self.pos - self.pos_sever_cnc)
        
        # 判断是否需要改变方向
        flag = self.pos - self.pos_sever_cnc
        if flag > 0:
            self.dir = -1
        elif flag < 0:
            self.dir = 1
        
        # 更新状态-> 1.移动
        self.status = 1

        if self.distance != 0:
            self.task_time = self.time_mv_ls[self.distance - 1]
            self.move()
            self.sum_move_distance += self.distance
        else:   # rgv 不需要移动，更新状态->2.上下料
            self.update_status_updown_material(cnc_ls, time)

        return self.num_sever_cnc

    def update_status_updown_material(self, cnc_ls, time):
        # 更新rgv位置为服务cnc的位置
        self.pos = self.pos_sever_cnc

        # 更新状态->上下料
        self.status = 2

        # 开始上料
        cnc_num, up_container, down_container = self.change_hand_status(self.num_sever_cnc, cnc_ls)
        
        self.update_container_info(cnc_num, up_container, down_container, time)

        # 更新上下料计时器
        if self.num_sever_cnc % 2 == 0:
            self.task_time = self.time_eve
        else:
            self.task_time = self.time_odd

        self.updown_material()
    
    def update_container_info(self, cnc_num, up_container, down_container, time):
        up_number = up_container[1]
        down_number = down_container[1]
        assert up_number != down_number
        up_type = up_container[0]
        down_type = down_container[0]
        # assert up_type != down_type
        # 如果放上去的是原料
        if up_type == 1:
            if self.type == 1:
                self.result_ls_task1[up_number-1][0] = up_number
                self.result_ls_task1[up_number-1][1] = cnc_num

                assert self.result_ls_task1[up_number-1][2] == 0

                self.result_ls_task1[up_number-1][2] = copy(time)

            if self.type == 2:
                self.result_ls_task2[up_number-1][0] = up_number
                # 更新原料为up_number执行的工序1的cnc编号
                self.result_ls_task2[up_number-1][1] = cnc_num
                # 更新原料为up_number执行的工序1的cnc上料开始时间
                self.result_ls_task2[up_number-1][2] = time

        elif up_type == 2:
            # 检测是否是同一份物料
            assert self.result_ls_task2[up_number-1][0] == up_number

            # 更新原料为up_number执行的工序2的cnc编号
            self.result_ls_task2[up_number-1][4] = cnc_num
            # 更新原料为up_number执行的工序2的cnc上料开始时间
            self.result_ls_task2[up_number-1][5] = time

        if down_type == 0:
            pass
        elif down_type == 2:
            if self.type == 1:

                assert self.result_ls_task1[down_number-1][1] == cnc_num
                # 更新原料为down_number执行的工序1的cnc编号
                self.result_ls_task1[down_number-1][1] = cnc_num
                # 更新原料为down_number执行的工序1的cnc下料开始时间

                assert self.result_ls_task1[down_number-1][3] == 0
                self.result_ls_task1[down_number-1][3] = copy(time)

            if self.type == 2:
                # assert self.result_ls_task2[down_number-1][1] == cnc_num
                # 更新原料为down_number执行的工序1的cnc编号
                self.result_ls_task2[down_number-1][1] = cnc_num
                # 更新原料为down_number执行的工序1的cnc下料开始时间
                self.result_ls_task2[down_number-1][3] = time

        elif down_type == 3:
            assert self.result_ls_task2[down_number-1][4] == cnc_num
            # 更新原料为down_number执行的工序2的cnc编号
            self.result_ls_task2[down_number-1][4] = cnc_num
            # 更新原料为down_number执行的工序2的cnc下料开始时间
            self.result_ls_task2[down_number-1][6] = time

    def update_status_wash_material(self):

        # 更新状态->清洗材料
        self.status = 3

        # 更新清洗任务计时器
        self.task_time = self.time_wash

        self.wash_material()
    
    def update_status_idle(self):
        self.status = 0

    def idle(self):
        self.idle_time += 1

    def move(self):
        self.task_time -= 1
        self.move_time += 1
    
    def updown_material(self):
        self.task_time -= 1
        self.updown_time += 1
    
    def wash_material(self):
        self.task_time -= 1
        self.wash_time += 1

    def get_task_time(self):
        return self.task_time

    def get_status(self):
        return self.status

    def select_cnc(self, wait_queue_ls, wait_set_ls, cnc_ls, mode='FIFO'):
        
        wait_queue, wait_queue_task1, wait_queue_task2 = wait_queue_ls
        wait_set, wait_set_task1, wait_set_task2 = wait_set_ls
        if mode == 'FIFO':
            k = self.FIFO(wait_queue, wait_queue_task1, wait_queue_task2, cnc_ls)
        if mode == 'HRN':
            k = self.HRN(wait_set, wait_set_task1, wait_set_task2, cnc_ls)
        if mode == 'SPW':
            k = self.SPW(wait_set, wait_set_task1, wait_set_task2, cnc_ls)
        if mode == 'STSPW':
            k = self.STSPW(wait_set, wait_set_task1, wait_set_task2, cnc_ls)
        if mode == 'BSTSPW':
            k = self.BSTSPW(wait_set, wait_set_task1, wait_set_task2, cnc_ls)
        return k
    
    def FIFO_task1(self, wait_queue):
        return wait_queue[0]

    def FIFO_task2(self, wait_queue_task1, wait_queue_task2, cnc_ls):
        # 手中有一道加工的料
        if self.hand_1[0] == 2 and self.hand_2[0] == 0 and wait_queue_task2 != []:
            return wait_queue_task2[0]
        # 手中无料
        if self.hand_1[0] == 0 and self.hand_2[0] == 0 and wait_queue_task1 != []:
            return wait_queue_task1[0]
        else:
            pass
        return -1
        
    def FIFO(self, wait_queue, wait_queue_task1, wait_queue_task2, cnc_ls):
        if self.type == 1:
            return self.FIFO_task1(wait_queue)
        else:
            return self.FIFO_task2(wait_queue_task1, wait_queue_task2, cnc_ls)
    
    def HRN(self, wait_set, wait_set_task1, wait_set_task2, cnc_ls):
        if self.type == 1:
            return self.HRN_task1(wait_set, cnc_ls)
        else:
            return self.HRN_task2(wait_set_task1, wait_set_task2, cnc_ls)
    
    def SPW(self, wait_set, wait_set_task1, wait_set_task2, cnc_ls):
        if self.type == 1:
            return self.SPW_task1(wait_set, cnc_ls)
        else:
            return self.SPW_task2(wait_set_task1, wait_set_task2, cnc_ls)
    
    def STSPW(self, wait_set, wait_set_task1, wait_set_task2, cnc_ls):
        if self.type == 1:
            return self.STSPW_task1(wait_set, cnc_ls)
        else:
            return self.STSPW_task2(wait_set_task1, wait_set_task2, cnc_ls)

    # 均衡时空最短路算法 balanced spatio-time min pathway algorithm
    def BSTSPW(self, wait_set, wait_set_task1, wait_set_task2, cnc_ls):
        if self.type == 1:
            return self.BSTSPW_task1(wait_set, cnc_ls)
        else:
            return self.BSTSPW_task2(wait_set_task1, wait_set_task2, cnc_ls)

    def BSTSPW_core(self, wait_set, cnc_ls, need_type=0):
        min_dist = self.max_dist
        left_min_dist = self.max_dist
        right_min_dist = self.max_dist
        mid_min_dist = self.max_dist
        num_mid_ready = 0
        num_left_ready = 0
        num_right_ready = 0
        k = -1
        left_k = -1
        right_k = -1
        mid_k = -1
        for cnc in cnc_ls:
            if cnc.get_type() != need_type:
                continue

            dist_s = abs(self.pos-cnc.get_pos())    # 空间距离
            dist_t = cnc.get_dist_time()            # 时间距离
            dist = max(dist_s, dist_t)              # 时空距离

            # 可以去
            if dist_s >= dist_t:
                # cnc在rgv的左边
                if cnc.get_pos() < self.pos:
                    num_left_ready += 1
                    if dist < left_min_dist:
                        left_min_dist = dist
                        left_k = cnc.num
                # cnc在rgv的右边
                elif cnc.get_pos() > self.pos:
                    num_right_ready += 1
                    if dist < right_min_dist:
                        right_min_dist = dist
                        right_k = cnc.num
                else:
                # rgv在cnc的中间
                    num_mid_ready += 1
                    if dist < mid_min_dist:
                        mid_min_dist = dist
                        mid_k = cnc.num

                if dist < min_dist:
                    min_dist = dist
                    k = cnc.num

        if num_mid_ready != 0:
            return mid_k

        if num_left_ready > num_right_ready and num_left_ready > num_mid_ready:
            k = left_k
        if num_right_ready > num_left_ready and num_right_ready > num_mid_ready:
            k = right_k
        if num_mid_ready > num_right_ready and num_mid_ready > num_left_ready:
            k = mid_k

        return k

    def BSTSPW_task1(self, wait_set, cnc_ls):
        return self.BSTSPW_core(wait_set, cnc_ls)
    
    def BSTSPW_task2(self, wait_set_task1, wait_set_task2, cnc_ls):
        # 手中有一块一道加工后的料
        if self.hand_1[0] == 2 and self.hand_2[0] == 0:
            return self.BSTSPW_core(wait_set_task2, cnc_ls, need_type=2)
        # 手中无料
        if self.hand_1[0] == 0 and self.hand_2[0] == 0:
            return self.BSTSPW_core(wait_set_task1, cnc_ls, need_type=1)
        return -1

    def STSPW_core(self, wait_set, cnc_ls, need_type = 0):
        minDist = self.max_dist
        k = -1
        for cnc in cnc_ls:
            if cnc.get_type() != need_type:
                continue            
            dist_s = abs(self.pos-cnc.get_pos())    # 空间距离
            dist_t = cnc.get_dist_time()            # 时间距离
            dist = max(dist_s, dist_t)              # 时空距离
            if dist < minDist:
                minDist = dist
                minDist_s = dist_s
                minDist_t = dist_t
                k = cnc.num
        # 检测能不能去，能去等话，就去；不能去，就在这待着。
        if minDist == self.max_dist:
            return -1
        else:
            # 暂时不能过去
            if minDist_s < minDist_t:
                return -1
            else:
            # 过去刚刚好
                return k
    
    def STSPW_task1(self, wait_set, cnc_ls):
        return self.STSPW_core(wait_set, cnc_ls)

    def STSPW_task2(self, wait_set_task1, wait_set_task2, cnc_ls):
        # 手中有一块一道加工后的料
        if self.hand_1[0] == 2 and self.hand_2[0] == 0:
            return self.STSPW_core(wait_set_task2, cnc_ls, need_type=2)
        # 手中无料
        if self.hand_1[0] == 0 and self.hand_2[0] == 0:
            return self.STSPW_core(wait_set_task1, cnc_ls, need_type=1)
        return -1

    def HRN_core(self, wait_set, cnc_ls):
        maxRR = 0
        k = -1
        for cnc in cnc_ls:
            if cnc.num not in wait_set:
                continue
            else:
                dist = abs(cnc.get_pos()-self.pos)
                mv_t = 0
                if dist >= 1:
                    mv_t = self.time_mv_ls[dist-1]
                if cnc.num % 2 == 0:
                    rr = 1 + cnc.get_response_ratio(mv_t, self.time_eve)
                else:
                    rr = 1 + cnc.get_response_ratio(mv_t, self.time_odd)
            if rr > maxRR:
                maxRR = rr
                k = cnc.num
        return k

    def HRN_task1(self, wait_set, cnc_ls):
        return self.HRN_core(wait_set, cnc_ls)
    
    def HRN_task2(self, wait_set_task1, wait_set_task2, cnc_ls):
        # 手中有一块一道加工后的料
        if self.hand_1[0] == 2 and self.hand_2[0] == 0 and len(wait_set_task2) != 0:
            return self.HRN_core(wait_set_task2, cnc_ls)
        # 手中无料
        if self.hand_1[0] == 0 and self.hand_2[0] == 0 and len(wait_set_task1) != 0:
            return self.HRN_core(wait_set_task1, cnc_ls)
        return -1
    
    def SPW_core(self, wait_set, cnc_ls):
        minDist = self.max_dist
        k = -1
        for cnc in cnc_ls:
            if cnc.num not in wait_set:
                continue
            else:
                dist = abs(self.pos-cnc.get_pos())
                if dist < minDist:
                    minDist = dist
                    k = cnc.num
        return k
        
    def SPW_task1(self, wait_set, cnc_ls):
        return self.SPW_core(wait_set, cnc_ls)
    
    def SPW_task2(self, wait_set_task1, wait_set_task2, cnc_ls):
        # 手中有一块一道加工后的料
        if self.hand_1[0] == 2 and self.hand_2[0] == 0 and len(wait_set_task2) != 0:
            return self.SPW_core(wait_set_task2, cnc_ls)
        # 手中无料
        if self.hand_1[0] == 0 and self.hand_2[0] == 0 and len(wait_set_task1) != 0:
            return self.SPW_core(wait_set_task1, cnc_ls)
        return -1

    def set_status(self, s):
        self.status = s
    

    def get_result(self, T):
        if self.type == 1:
            self.result_ls = copy(self.result_ls_task1)
            self.used_material_ls = copy(self.result_ls_task1)
            for r in reversed(self.result_ls):
                if r[-1] == 0:
                    self.result_ls.remove(r)
                if r[0] == 0:
                    self.used_material_ls.remove(r)
            
            self.num_result = len(self.result_ls)
            self.num_material = len(self.used_material_ls)

            return self.num_result

        if self.type == 2:
            self.result_ls = copy(self.result_ls_task2)
            self.used_material_ls = copy(self.result_ls_task2)

            for r in reversed(self.result_ls):
                if r[-1] == 0:
                    self.result_ls.remove(r)
                if r[0] == 0:
                    self.used_material_ls.remove(r)
            
            self.num_result = len(self.result_ls)
            self.num_material = len(self.used_material_ls)

            return self.num_result

    def get_result_ls_task1(self, T):
        self.get_result(T)
        return self.result_ls
    
    def get_used_material_ls(self, T):
        self.get_result(T)
        return self.used_material_ls

    def get_result_ls_task2(self, T):
        self.get_result(T)
        return self.result_ls

    def get_mean_wait_time(self, cnc_ls):
        wt_ls = []
        for cnc in cnc_ls:
            wt_ls += cnc.wait_time_ls
        if wt_ls != []:
            self.cnc_mean_wait_time = np.mean(wt_ls)

        return self.cnc_mean_wait_time
    
    def get_sum_wait_time(self, cnc_ls):
        wt_ls = []
        for cnc in cnc_ls:
            wt_ls += cnc.wait_time_ls
        if wt_ls != []:
            self.cnc_sum_wait_time = np.sum(wt_ls)

        return self.cnc_sum_wait_time/len(cnc_ls)
    
    def get_std_wait_time(self, cnc_ls):
        wt_ls = []
        for cnc in cnc_ls:
            wt_ls += cnc.wait_time_ls
        if wt_ls != []:
            self.cnc_std_wait_time = np.std(wt_ls)

        return self.cnc_std_wait_time

    def stats(self, cnc_ls, T):
        info = []
        # cnc
        self.cnc_mean_wait_time = self.get_mean_wait_time(cnc_ls)
        self.num_result = self.get_result(T)
        # rgv
        self.pre_idle_time = self.idle_time/T
        self.pre_move_time = self.move_time/T
        self.pre_updown_time = self.updown_time/T
        self.pre_wash_time = self.wash_time/T
        self.avg_distance = self.sum_move_distance/self.num_result
        
        info = [self.cnc_mean_wait_time, self.num_result, self.pre_idle_time, self.pre_move_time, self.pre_updown_time, self.pre_wash_time, self.avg_distance]
        return info
