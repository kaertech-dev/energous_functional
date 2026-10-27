from tkinter import *
from tkinter import ttk
from tkinter import filedialog
from tkinter import messagebox

from datetime import datetime
import pymysql
from pymysql.cursors import DictCursor

import csv
import yaml
import re # regular expressions

import os
import sys
import signal
import serial.tools.list_ports

import tag_test
import mfgdb

CONFIG_FILE = os.path.join("config","eSense_FT_config.yaml")
DB_CONFIG_FILE = os.path.join("config", "db.yaml")
KDB_CONFIG_FILE = os.path.join("config", "k_db.yaml")
LOG_PATH = "logs"

REG_EX_LEN = None
REG_EX = None

STOP_TAG_TEST = False
TESTING_TAGS = False
STORE_TO_DB = 1

SCAN_WATCH = None

TEST_EVENT_QUEUE = []

result_list = []
tags_tested = [0 for i in range(25)]
num_tags = 0

test_mode = 'DEVELOPMENT'
login_details = {'operator_en': '', 'shift': ''}
tag_db_details = {}
with open(KDB_CONFIG_FILE, encoding="utf-8") as dbFile:
    kdb_params = yaml.safe_load(dbFile)

db_model = kdb_params['model']
db_table = kdb_params['table']
db_config = {
    'host': kdb_params['host'],
    'database': kdb_params['schema'],
    'user': 'labeling',
    'password': 'labeling',
    'autocommit': False
}

# create a class deriving from TK to be the root
class EnEsnsTest(Tk):
    def __init__(self, screenName = None, baseName = None, className = "Tk", useTk = True, sync = False, use = None):
        super().__init__(screenName, baseName, className, useTk, sync, use)
        
        self.frame = None
        self.frame_cache = {}
        self.configParam = None
        self.internal_setup()
        self.gui_setup()
        self.bind("<<ToggleMongo>>", self.toggle_mongo_root_helper)

    def toggle_mongo_root_helper(self, event):
        global REG_EX, REG_EX_LEN
        if TESTING_TAGS == False:
            self.frame_cache[TestSetup].clear_button_helper()
        if STORE_TO_DB.get() == "1":
            REG_EX = self.configParam["tagID"]["regEx"]
            REG_EX_LEN = self.configParam["tagID"]["regExLen"]
        else:
            REG_EX = self.configParam["tagID"]["regEx_no_db"]
            REG_EX_LEN = self.configParam["tagID"]["regExLen_no_db"]   
    
    def dismissChecker(self):
        self.configParam["bridge"]["tx_com_port"] = tag_test.DEFAULT_SERIAL.get()
        self.configParam["upload_to_db"] = STORE_TO_DB.get()
        self.configParam["tagID"]["scan_watch"] = SCAN_WATCH.get()
        with open(CONFIG_FILE, 'w') as cfile:
            yaml.dump(self.configParam, cfile)

        self.after_idle(ft_safe_exit, 130)
    
    def internal_setup(self):
        global REG_EX_LEN
        global REG_EX
        global STORE_TO_DB
        global SCAN_WATCH

        with open(CONFIG_FILE, encoding="utf-8") as config:
            self.configParam = yaml.safe_load(config)

        with open(DB_CONFIG_FILE, encoding="utf-8") as dbFile:
            self.dbParam = yaml.safe_load(dbFile)
        
        tag_test.DEFAULT_SERIAL = StringVar(value=self.configParam["bridge"]["tx_com_port"])
        
        STORE_TO_DB = StringVar(value=self.configParam["upload_to_db"])

        if STORE_TO_DB.get() == "1":
            REG_EX = self.configParam["tagID"]["regEx"]
            REG_EX_LEN = self.configParam["tagID"]["regExLen"]
        else:
            REG_EX = self.configParam["tagID"]["regEx_no_db"]
            REG_EX_LEN = self.configParam["tagID"]["regExLen_no_db"]

        SCAN_WATCH = IntVar(value=self.configParam["tagID"]["scan_watch"])   

    def test_Serial(self):
        found = True
        try:
            SERIAL_HANDLE = serial.Serial(
                f"{tag_test.DEFAULT_SERIAL.get()}", 115200, timeout=0.5)
        except Exception as error:
            messagebox.showwarning(title="No Serial Cable", message="Com Port " + self.configParam["bridge"]["tx_com_port"] + " not detected")
            found = False

        if tag_test.SERIAL_HANDLE is not None:
            tag_test.SERIAL_HANDLE.close()

        return found

    def gui_setup(self):
        self.title("Energous Tag Test")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        # TODO: customization can help easily identiy tool, but is not neccesary
        self.change_frame(TestSetup)
        # if "main_menu_frame" in self.frame_cache:
        #     self.change_frame(self.frame_cache["main_menu_frame"])
        # else:
        #     self.frame_cache["main_menu_frame"] = MainMenu(self)
    
    def change_frame(self, frame_name):
        if self.frame is not None:
            # print("change_frame: not first frame, clear current")
            self.frame.grid_remove()

        if frame_name in self.frame_cache:
            # change to it, by regridding
            # print("change_frame: old frame, regrid")
            self.frame = self.frame_cache[frame_name]
            self.frame.grid() 
        else:
            # init
            # print("change_frame: new frame, make new")
            self.frame_cache[frame_name] = frame_name(self)
            self.frame = self.frame_cache[frame_name]

        

class TestSetup(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, padding="3 3 12 12")

        # TODO: how can label text grow? its a bit small

        self.pStore = parent

        self.greet_label = ttk.Label(self, text="Scan Tags")

        self.test_mode = ttk.Label(self, text='DEVELOPMENT', background='cyan', font=('Segoe UI', 15, "bold"))

        self.oprtr_en = StringVar()
        self.oprtr_en_obj = ttk.Entry(self, foreground='grey', textvariable=self.oprtr_en, width=25)
        self.oprtr_en_obj.insert(0, 'OPRTR_EN')
        self.oprtr_en_obj.bind("<FocusIn>", self.oprtr_foc_in)
        self.oprtr_en_obj.bind("<FocusOut>", self.oprtr_foc_out)

        self.shift = StringVar(self)
        self.shift_obj = ttk.Entry(self, foreground='grey', textvariable=self.shift, width=25)
        self.shift_obj.insert(0, 'SHIFT')
        self.shift_obj.bind("<FocusIn>", self.shift_foc_in)
        self.shift_obj.bind("<FocusOut>", self.shift_foc_out)

        self.login_button = ttk.Button(self, width=25, text="Login", command=self.get_login)

        self.tag_input_text = StringVar()
        self.tag_input_obj = ttk.Entry(self, textvariable=self.tag_input_text, width=25)

        self.clear_button = ttk.Button(self, width=25, text="Clear", command=self.clear_button_helper)
        self.load_next_button = ttk.Button(self, width=25, text="Scan Next Batch", command=self.add_queue_helper)
        self.start_button = ttk.Button(self, width=25, text="Start Test", command=self.start_button_helper)

        self.progress_txt = ttk.Label(self, text="Placeholder", anchor="center")
        self.progress_obj = ttk.Progressbar(self, orient=HORIZONTAL, length=200, mode='determinate', maximum=6)

        for child in self.winfo_children():
            child.grid_configure(padx=5, pady=5)

        self.tag_frames = [0 for l in range(25)]
        self.next_batch = []
        self.next_batch_len = 0

        let = ["A", "B", "C", "D", "E"]
        letNum = 0
        num = 1
        for fN in range(25):
            spotLabel = let[letNum]+str(num)
            self.tag_frames[fN] = ttk.Frame(self, relief='solid', borderwidth=5)
            self.tag_frames[fN].tagText = StringVar()
            self.tag_frames[fN].tagObject = ttk.Label(self.tag_frames[fN], background="grey", width=25, anchor="center", textvariable=self.tag_frames[fN].tagText)
            self.tag_frames[fN].spotLabel = ttk.Label(self.tag_frames[fN], background="grey", width=25, anchor="center", text=spotLabel)
            num += 1
            if num == 6:
                num = 1
                letNum += 1

        self.current_tag_cnt = 0

        # TODO: when testing is done, redo into loop
        self.columnconfigure(0, weight=100)
        self.columnconfigure(1, weight=1)
        self.columnconfigure(2, weight=1)
        self.columnconfigure(3, weight=1)
        self.columnconfigure(4, weight=1)
        self.columnconfigure(5, weight=1)
        self.columnconfigure(6, weight=100)

        
        self.rowconfigure(0, weight= 100)
        self.rowconfigure(1, weight=1)
        self.rowconfigure(2, weight=50)
        self.rowconfigure(3, weight=50)
        self.rowconfigure(4, weight=50)
        self.rowconfigure(5, weight=50)
        self.rowconfigure(6, weight=50)
        self.rowconfigure(7, weight=50)
        self.rowconfigure(8, weight=50)
        self.rowconfigure(9, weight=1)
        self.rowconfigure(10, weight=1)
        self.rowconfigure(11, weight=100)

        self.grid(column=0, row=0, sticky=(N, W, E, S))

        self.test_mode.grid(column=1, row=0)
        self.oprtr_en_obj.grid(column=3, row=0)
        self.shift_obj.grid(column=4, row=0)
        self.login_button.grid(column=5, row=0)

        self.greet_label.grid(column=0, row=1, columnspan=7)
        rowCnt = 1
        for e in range(25):
            if(e%5 == 0):
                rowCnt += 1

            self.tag_frames[e].grid(column=(e%5)+1, row=rowCnt, sticky=(N, W, E, S))
            self.tag_frames[e].columnconfigure(0, weight=1)
            
            self.tag_frames[e].rowconfigure(0, weight= 1)
            self.tag_frames[e].rowconfigure(1, weight=1)

            self.tag_frames[e].tagObject.grid(column=0, row=0, sticky=(N, W, E, S))
            self.tag_frames[e].spotLabel.grid(column=0, row=1, sticky=(N, W, E, S))
            
        
        self.clear_button.grid(column=1, row=8, sticky=(N, W, E, S))
        # self.start_button.grid(column=5, row=8, sticky=(N, W, E, S))
        self.load_next_button.grid(column=5, row=8, sticky=(N, W, E, S))
        self.load_next_button.state(['disabled'])
        self.start_button.grid(column=3, row=8, sticky=(N, W, E, S))
        self.start_button.state(['disabled'])

        self.tag_input_obj.grid(column=3, row=7, sticky=(N, W, E, S))
        # self.tag_input_obj.focus_set()
        self.tag_input_obj.bind("<Return>", self.scan_enter)
        self.pStore.bind("<Map>", lambda e: self.tag_input_obj.focus_set())
        self.tag_input_text.trace_add("write", self.scan_watch)

        self.progress_txt.grid_remove()
        self.progress_obj.grid_remove()

    def write_csv(self, log_file):
        attempt = 1
        while attempt < 4:
            try: 
                with open(log_file, "a+", newline="", encoding="utf-8") as log:
                    headers = ["Time_Stamp", "ENID", "BD_Address", "Board_Serial", "RSSI", "TTFA", "Adv_Count", "Fail_Reason", "Final_Result"]
                    log.seek(0)
                    writer = csv.DictWriter(log, fieldnames=headers)
                    try:
                        next(csv.reader(log, delimiter=","))
                    except StopIteration:
                        writer.writeheader()
                    
                    for i in range(num_tags):
                        writer.writerow(tags_tested[i])
            except PermissionError as pem_err:
                messagebox.showerror(message=f"While writing to log file, saw:\n\n{pem_err}\n\nAttempt {attempt}/3\n\nIs the log file closed?", title="Error Writing to CSV")
                attempt += 1

            except Exception as error:
                messagebox.showerror(message=f"While writing to log file, saw:\n\n{error}\n\nAttempt {attempt}/3\n\nTrying again...", title="Error Writing to CSV")
                attempt += 1
            else:
                return

        messagebox.showerror(message=f"Log Writing Failed 3 Times. Contact Engineering.", title="Log Writing Failure")
        self.pStore.dismissChecker()

    def setMode(self, mode):
        global test_mode
        if mode == 'Development':
            test_mode = 'DEVELOPMENT'
            self.test_mode.config(text=mode.upper(), background='cyan')
        else:
            test_mode = 'PRODUCTION'
            self.test_mode.config(text=mode.upper(), background='yellow')

    def oprtr_foc_in(self, event):
        if self.oprtr_en_obj.get() == 'OPRTR_EN':
            self.oprtr_en.set("")
            self.oprtr_en_obj.config(foreground='black')
    
    def oprtr_foc_out(self, event):
        if not self.oprtr_en_obj.get():
            self.oprtr_en_obj.insert(0, 'OPRTR_EN')
            self.oprtr_en_obj.config(foreground='grey')

    def shift_foc_in(self, event):
        if self.shift_obj.get() == 'SHIFT':
            self.shift.set("")
            self.shift_obj.config(foreground='black')

    def shift_foc_out(self, event):
        if not self.shift_obj.get():
            self.shift_obj.insert(0, 'SHIFT')
            self.shift_obj.config(foreground='grey')

    def get_login(self):
        global login_details
        oprtr_r = self.oprtr_en.get().strip()
        if len(oprtr_r) == 0 or oprtr_r == 'OPRTR_EN':
            messagebox.showerror("Error", "No value for OPRTR_EN")
            return
        
        shift_r = self.shift.get().upper()
        if shift_r != 'A' and shift_r != 'B':
            messagebox.showerror("Error", "Invalid value for SHIFT")
            return

        if self.login_button['text'] == 'Login':
            login_details['operator_en'] = oprtr_r
            login_details['shift'] = shift_r
            self.oprtr_en_obj.config(state='readonly')
            self.shift_obj.config(state='readonly')
            print('Logged in:', oprtr_r, shift_r)
            self.login_button.config(text='Logout')
        else:
            login_details['operator_en'] = ''
            login_details['shift'] = ''
            self.oprtr_en_obj.config(state='normal')
            self.shift_obj.config(state='normal')
            print('Logged out')
            self.login_button.config(text='Login')
    
    def log_setup(self):
        self.today = datetime.today().strftime("%Y-%m-%d")
        self.log_file = f"{LOG_PATH}/{self.pStore.configParam['station']}_{self.today}.csv"
    
    def scan_watch(*args):
        if (SCAN_WATCH.get()) and (len(args[0].tag_input_text.get()) == REG_EX_LEN):
            args[0].scan_enter("<Return>") # TODO: verify
    
    def scan_enter(self, event): # TODO: how handle case for letters A-F
        global tag_db_details
        tag_id = self.tag_input_obj.get().upper()
        # validate what is in the tag
        if self.current_tag_cnt < 25: # if room to add
            if bool(re.match(REG_EX, self.tag_input_obj.get())):
                # correct address
                # check for duplicates
                if self.is_duplicate_tag(tag_id):
                    messagebox.showerror(message="Duplicate ID!", title="Duplicate!")
                else:
                    # if self.test_mode == 'PRODUCTION':
                    db_deets = self.get_db_status(tag_id)
                    if test_mode == 'PRODUCTION' and not db_deets:
                        return
                    self.tag_frames[self.current_tag_cnt].tagText.set(tag_id) 
                    self.tag_frames[self.current_tag_cnt].tagObject.config(background='')
                    self.tag_frames[self.current_tag_cnt].spotLabel.config(background='')
                    tag_db_details[tag_id] = db_deets
                    # print(tag_db_details)
                    self.current_tag_cnt += 1
                    if (self.current_tag_cnt > 0):
                        self.start_button.state(['!disabled'])
            else:
                #incorrect address
                messagebox.showerror(message="Invalid ID!", title="Invalid!")
        else:
            messagebox.showerror(message="Test Bed Full!", title="Test Full!")
        
        self.tag_input_obj.delete(0, 'end')

    def is_duplicate_tag(self, BT):
        for d in range(self.current_tag_cnt):
            if(self.tag_frames[d].tagText.get() == BT):
                return True
        return False

    def get_db_status(self, product_id):
        with pymysql.connect(**db_config) as dbconn:
            with dbconn.cursor(DictCursor) as cursor:
                # get serial from id_log
                first_query = f" SELECT `serial_num` FROM `{kdb_params['idTable']}` WHERE `{kdb_params['idColumn']}` " + "= %s AND `serial_num` NOT LIKE %s "
                cursor.execute(first_query, (product_id, '\\%_\\%'))
                response = cursor.fetchone()
                if not response:
                    messagebox.showerror("Error", "No serial number in database")
                    return {}
                print('f---', response)
                serial_num = response['serial_num']

                # get po_num from main, check previous stations
                second_query = f" SELECT * FROM `{db_model}_main`" + " WHERE `serial_num` = %s"
                cursor.execute(second_query, (serial_num,))
                station_list = cursor.fetchone()
                ponum = station_list['po_num']
                print('s---', station_list)

                didNotPass = []
                for head, value in station_list.items():
                    if head == 'serial_num' or head == 'po_num':
                        pass
                    elif head == db_table:
                        break
                    elif value == 0:
                        didNotPass.append(head)

                if len(didNotPass) > 0:
                    messagebox.showerror("Error", f"Unit did not pass {', '.join(didNotPass)}")
                    # return {'serial_num': serial_num, 'po_num': ponum, 'test_rep': -1}
                    return {}
        
                # check if retest
                table_name = f"`{db_model}_{db_table}`"
                third_query = " SELECT `serial_num`, `po_num`, `test_rep`, `status` FROM " + table_name + " WHERE `serial_num` LIKE %s ORDER BY `test_rep` DESC "
                cursor.execute(third_query, (f"{serial_num}%",))
                trep = cursor.fetchall()

                if len(trep) == 0:
                    curr_trep = 1
                elif trep[0]['test_rep'] >= 3:
                    messagebox.showerror("Error", 'No more retests allowed')
                    # return {'serial_num': serial_num, 'po_num': ponum, 'test_rep': -1}
                    return {}
                elif trep[0]['status'] == 1:
                    messagebox.showerror("Error", 'Unit already passed')
                    # return {'serial_num': serial_num, 'po_num': ponum, 'test_rep': -1}
                    return {}
                else:
                    curr_trep = len(trep) + 1

                print('t---', trep)
                return {'serial_num': serial_num, 'po_num': ponum, 'test_rep': curr_trep}

    def add_queue_helper(self):
        # Open new window with frame
        add_queue_window = Toplevel(self.pStore)
        modal_frame = AddToQueueFrame(add_queue_window, self.next_batch)
        # modal_frame.cap = self.cap
        add_queue_window.transient(self)
        add_queue_window.wait_visibility()
        add_queue_window.grab_set()
        add_queue_window.wait_window()

        self.next_batch = modal_frame.tag_frames
        self.next_batch_len = len([x for x in modal_frame.tag_frames if x.tagText.get() != ''])
        # print('new batch:', self.next_batch_len)
        if self.next_batch_len > 1:
            self.load_next_button.configure(text=f"Next batch: {self.next_batch_len} units")
        elif self.next_batch_len == 1:
            self.load_next_button.configure(text=f"Next batch: 1 unit")
        else:
            self.load_next_button.configure(text="Scan Next Batch")
        
        add_queue_window.grab_release()
        add_queue_window.destroy()

    def load_queue_helper(self):
        for i, x in enumerate(self.next_batch):
            cell_txt = x.tagText.get()
            if cell_txt != '':
                self.tag_frames[i].tagText.set(cell_txt.upper()) 
                self.tag_frames[i].tagObject.config(background='')
                self.tag_frames[i].spotLabel.config(background='')
                self.current_tag_cnt += 1

        if(self.current_tag_cnt > 0):
            self.start_button.state(['!disabled'])

        self.load_next_button.configure(text="Scan Next Batch", command=self.add_queue_helper)
        self.load_next_button.state(['disabled'])
        self.next_batch = []
        self.next_batch_len = 0

    def clear_button_helper(self):
        self.tag_input_obj.delete(0, 'end')
        for clr in range(self.current_tag_cnt):
            self.tag_frames[clr].tagText.set("")
            self.tag_frames[clr].tagObject.config(background="grey")
            self.tag_frames[clr].spotLabel.config(background="grey")
        self.current_tag_cnt = 0
        self.start_button.state(['disabled'])
    
    def start_button_helper(self):
        if test_mode == 'PRODUCTION' and not login_details.get('operator_en'):
            messagebox.showerror(message="Pleae enter login details", title="No Login")
            return
        if(self.pStore.test_Serial() == False):
            messagebox.showerror(message="Transmitter is not connected to PC", title="Invalid Serial")
            return
        if STORE_TO_DB.get() == "1" and (mfgdb.is_db_up(self.pStore.dbParam) == False):
            messagebox.showerror(message="MongoDB is not connected", title="No MongoDB")
            return
        # disable normal functions
        # self.start_button.state(['disabled'])
        self.start_button.configure(command=self.stop_button_helper, text="Stop")
        self.clear_button.state(['disabled'])
        self.tag_input_obj.state(['disabled'])
        self.login_button.state(['disabled'])
        
        # format screen for waiting
        for st in range(self.current_tag_cnt):
            self.tag_frames[st].tagObject.config(background="lightblue")
            self.tag_frames[st].spotLabel.config(background="lightblue")

        self.progress_txt.grid(column=1, row=9, sticky=(N, W, E, S), columnspan=5)
        self.progress_obj.grid(column=1, row=10, sticky=(N, W, E, S), columnspan=5)

        # perform test
        global tags_tested
        global num_tags
        global result_list
        global STOP_TAG_TEST
        global TESTING_TAGS

        self.log_setup()
        num_tags = self.current_tag_cnt
        timeForTest = datetime.today()
        if STORE_TO_DB.get() == "1":
            for i in range(num_tags):
                tempBSN = self.tag_frames[i].tagText.get()
                pdt = self.pStore.dbParam.get("product").lower()
                tags_tested[i] = {"Time_Stamp": timeForTest, 
                                "ENID": str(mfgdb.get_enid_from_board_sn(self.pStore.dbParam, pdt, tempBSN)), 
                                "BD_Address": str(mfgdb.get_bdaddress_from_board_sn(self.pStore.dbParam, pdt, tempBSN)), 
                                "Board_Serial": tempBSN, 
                                "RSSI": 0,
                                "TTFA": 0,
                                "Adv_Count": 0,
                                "Fail_Reason": "Def", 
                                "Final_Result" : "Fail"}
        else:
            for i in range(num_tags):
                tempEID = self.tag_frames[i].tagText.get()
                pdt = self.pStore.dbParam.get("product").lower()
                tags_tested[i] = {"Time_Stamp": timeForTest, 
                                "ENID": tempEID, 
                                "BD_Address": "No DB", 
                                "Board_Serial": "No DB", 
                                "RSSI": 0,
                                "TTFA": 0,
                                "Adv_Count": 0,
                                "Fail_Reason": "Def", 
                                "Final_Result" : "Fail"}
        
        STOP_TAG_TEST = False
        TESTING_TAGS = True
        self.after_idle(self.test_tags_helper)
    
    def stop_button_helper(self):
        global STOP_TAG_TEST, TESTING_TAGS, TEST_EVENT_QUEUE
        STOP_TAG_TEST = True
        TESTING_TAGS = False

        for i in range(num_tags):
            result_list.append(0)

        for event in TEST_EVENT_QUEUE:
            self.after_cancel(event)

        TEST_EVENT_QUEUE = []

        self.after(200, lambda: tag_test.tag_test_main("reset"))

        self.post_test_helper()
    
    def post_test_helper(self):
        self.pStore.change_frame(ResultScreen)
        self.start_button.configure(command=self.start_button_helper, text="Start")
        self.start_button.state(['disabled'])
        self.clear_button.state(['!disabled'])
        self.tag_input_obj.state(['!disabled'])
        self.login_button.state(['!disabled'])

        if self.next_batch_len == 0:
            self.load_next_button.configure(text="Scan Next Batch")
            self.load_next_button.state(['disabled'])
        else:
            self.load_next_button.configure(text=f"Load next: {self.next_batch_len} units", command=self.load_queue_helper)
            self.load_next_button.state(['!disabled'])

        # for st in range(self.current_tag_cnt):
        #     self.tag_frames[st].tagObject.config(background="grey")
        #     self.tag_frames[st].spotLabel.config(background="grey")
        #     self.tag_frames[st].tagText.set("")
        self.clear_button_helper()

        self.current_tag_cnt = 0

        self.progress_txt.grid_remove()
        self.progress_obj.grid_remove()
        global TESTING_TAGS
        TESTING_TAGS = False
        global TEST_EVENT_QUEUE 
        TEST_EVENT_QUEUE = []

    def test_tags_store_results(self):
        self.progress_obj['value'] = 8
        self.progress_txt['text']= "Storing Results"
        self.start_button.state(['disabled'])
        self.write_csv(self.log_file)
        
        if self.pStore.dbParam and STORE_TO_DB.get() == "1":
            Board_sn_regex = self.pStore.dbParam.get("Board_sn_regex", None)
            if not Board_sn_regex or Board_sn_regex != self.pStore.configParam["tagID"]["regEx"]:
                messagebox.showwarning(message="Invalid MongoDB config, skipping upload...", title="Invalid MongoDB")
            else:
                # Update the database
                for i in range(num_tags):
                    if mfgdb.write_db(tags_tested[i], self.pStore.configParam["station"], self.pStore.dbParam) == False:
                        # TODO: what to do if db lost?
                        messagebox.showerror(message="MongoDB could not be reached", title="No MongoDB")
                        break

        self.after(1, self.post_test_helper)
    
    def test_tags_end_BLE_scan(self):
        if STOP_TAG_TEST:
            self.after(1, lambda: tag_test.tag_test_main("reset"))
            return

        global tags_tested
        global result_list
        global num_tags

        self.progress_obj['value'] = 7
        self.progress_txt['text']= "Gather Results"

        result_list = []

        raw_results = tag_test.tag_test_main("tagTest 0")
        if not raw_results:
            self.after(1, self.test_tags_store_results)
            return
        res = raw_results.split("\n")
        for c in range(1, len(res)-1):
            res[c] = res[c].strip("\r") # Three values seen, only using the ENID for now

        if STORE_TO_DB.get() == "1": 
            for i in range(num_tags):
                pass_flag = 0
                j = 0
                while j+2 < (len(res)-1):
                    j += 2
                    enIDT, bdT, tTS = res[j].split(',')
                    rssiArr = res[j+1].split(',')
                    if (tags_tested[i]["ENID"] == enIDT.upper()) and (tags_tested[i]["BD_Address"] == bdT.upper()): # both digital IDs match
                        tags_tested[i]["TTFA"] = int(tTS)
                        tags_tested[i]["RSSI"] =  -1 * average_helper(rssiArr)
                        tags_tested[i]["Adv_Count"] = sum([1 for x in rssiArr if x != "0"])

                        temp_str = ""
                        limit_check_pass = 1

                        if tags_tested[i]["TTFA"] < self.pStore.configParam["limits"]["TTFA_min"]:
                            temp_str += "TTFA LOW--"
                            limit_check_pass = 0

                        if tags_tested[i]["TTFA"] > self.pStore.configParam["limits"]["TTFA_max"]:
                            temp_str += "TTFA HIGH--"
                            limit_check_pass = 0

                        if tags_tested[i]["RSSI"] < self.pStore.configParam["limits"]["RSSI_min"]:
                            temp_str += "RSSI LOW--"
                            limit_check_pass = 0       

                        if tags_tested[i]["RSSI"] > self.pStore.configParam["limits"]["RSSI_max"]:
                            temp_str += "RSSI HIGH--"
                            limit_check_pass = 0

                        if tags_tested[i]["Adv_Count"] < self.pStore.configParam["limits"]["Adv_Count_min"]:
                            temp_str += "Adv_Count LOW--"
                            limit_check_pass = 0  

                        if tags_tested[i]["Adv_Count"] > self.pStore.configParam["limits"]["Adv_Count_max"]:
                            temp_str += "Adv_Count HIGH--"
                            limit_check_pass = 0     

                        if limit_check_pass:
                            pass_flag = 1
                            tags_tested[i]["Fail_Reason"] = "N/A"
                            tags_tested[i]["Final_Result"] = "Pass"
                        else:
                            pass_flag = 0
                            tags_tested[i]["Fail_Reason"] = temp_str
                            tags_tested[i]["Final_Result"] = "Fail"
                        break
                
                result_list.append(pass_flag)
        else:
            for i in range(num_tags):
                pass_flag = 0
                j = 0
                while j+2 < (len(res)-1):
                    j += 2
                    enIDT, bdT, tTS = res[j].split(',')
                    rssiArr = res[j+1].split(',')
                    if (tags_tested[i]["ENID"] == enIDT.upper()): # both digital IDs match
                        tags_tested[i]["BD_Address"] = bdT
                        tags_tested[i]["TTFA"] = int(tTS)
                        tags_tested[i]["RSSI"] =  -1 * average_helper(rssiArr)
                        tags_tested[i]["Adv_Count"] = sum([1 for x in rssiArr if x != "0"])

                        temp_str = ""
                        limit_check_pass = 1

                        if tags_tested[i]["TTFA"] < self.pStore.configParam["limits"]["TTFA_min"]:
                            temp_str += "TTFA LOW--"
                            limit_check_pass = 0

                        if tags_tested[i]["TTFA"] > self.pStore.configParam["limits"]["TTFA_max"]:
                            temp_str += "TTFA HIGH--"
                            limit_check_pass = 0

                        if tags_tested[i]["RSSI"] < self.pStore.configParam["limits"]["RSSI_min"]:
                            temp_str += "RSSI LOW--"
                            limit_check_pass = 0       

                        if tags_tested[i]["RSSI"] > self.pStore.configParam["limits"]["RSSI_max"]:
                            temp_str += "RSSI HIGH--"
                            limit_check_pass = 0

                        if tags_tested[i]["Adv_Count"] < self.pStore.configParam["limits"]["Adv_Count_min"]:
                            temp_str += "Adv_Count LOW--"
                            limit_check_pass = 0  

                        if tags_tested[i]["Adv_Count"] > self.pStore.configParam["limits"]["Adv_Count_max"]:
                            temp_str += "Adv_Count HIGH--"
                            limit_check_pass = 0     

                        if limit_check_pass:
                            pass_flag = 1
                            tags_tested[i]["Fail_Reason"] = "N/A"
                            tags_tested[i]["Final_Result"] = "Pass"
                        else:
                            pass_flag = 0
                            tags_tested[i]["Fail_Reason"] = temp_str
                            tags_tested[i]["Final_Result"] = "Fail"
                        break
                
                result_list.append(pass_flag)

        for i in range(num_tags):
            if tags_tested[i]["Final_Result"] == "Fail" :
                if tags_tested[i]["Fail_Reason"] == "Def":
                    if (tags_tested[i]["ENID"] == "DUPE") or (tags_tested[i]["BD_Address"] == "DUPE"):
                        tags_tested[i]["Fail_Reason"] += "DB duplicate--"
                    elif (tags_tested[i]["ENID"] == "N/A") or (tags_tested[i]["BD_Address"] == "N/A"):
                        tags_tested[i]["Fail_Reason"] += "DB fetch fail--"
                    elif (tags_tested[i]["ENID"] == "ND") or (tags_tested[i]["BD_Address"] == "ND"):
                        tags_tested[i]["Fail_Reason"] = "BD_Address not in DB" 
                    else:
                        tags_tested[i]["Fail_Reason"] =  "No Adv Rcvd"

        self.after(1, self.test_tags_store_results)
    
    def test_tags_clearWave(self):
        global TEST_EVENT_QUEUE
        if STOP_TAG_TEST:
            self.after(1, lambda: tag_test.tag_test_main("reset"))
            return

        self.progress_obj['value'] = 6
        self.progress_txt['text']= "Stop Test"
        TEST_EVENT_QUEUE.append(self.after(1, self.test_tags_end_BLE_scan))
        TEST_EVENT_QUEUE.append(self.after_idle(lambda: tag_test.tag_test_main("energous pam cw 0")))
    
    def test_tags_set_wave(self):
        global TEST_EVENT_QUEUE
        if STOP_TAG_TEST:
            self.after(1, lambda: tag_test.tag_test_main("reset"))
            return

        self.progress_obj['value'] = 5
        self.progress_txt['text']= "Testing..."
        TEST_EVENT_QUEUE.append(self.after(self.pStore.configParam["delays"]["setWaveWptDelay"] + 10, lambda: tag_test.tag_test_main("energous pam set_pa " + f'{self.pStore.configParam["bridge"]["setPaVal"]}')))
        TEST_EVENT_QUEUE.append(self.after(self.pStore.configParam["delays"]["setWaveWptDelay"], lambda: tag_test.tag_test_main("energous pam cw 1")))
        TEST_EVENT_QUEUE.append(self.after(self.pStore.configParam["delays"]["endTestBleDelay"], self.test_tags_clearWave))

    def test_tags_start_BLE_scan(self):
        global TEST_EVENT_QUEUE
        if STOP_TAG_TEST:
            self.after(1, lambda: tag_test.tag_test_main("reset"))
            return

        self.progress_obj['value'] = 4
        self.progress_txt['text']= "Start BLE Scan"
        TEST_EVENT_QUEUE.append(self.after(1, lambda: tag_test.tag_test_main("tagTest 1")))
        TEST_EVENT_QUEUE.append(self.after(self.pStore.configParam["delays"]["setWavePaDelay"], self.test_tags_set_wave))

    def test_tags_soak_off(self):
        global TEST_EVENT_QUEUE
        if STOP_TAG_TEST:
            self.after(1, lambda: tag_test.tag_test_main("reset"))
            return
        
        self.progress_obj['value'] = 3
        self.progress_txt['text']= "Stop Soak"

        TEST_EVENT_QUEUE.append(self.after(1, lambda: tag_test.tag_test_main("energous pam cw 0")))
        TEST_EVENT_QUEUE.append(self.after(self.pStore.configParam["delays"]["startBleDelay"], self.test_tags_start_BLE_scan))

    def test_tags_soak_on(self):
        global TEST_EVENT_QUEUE
        if STOP_TAG_TEST:
            self.after(1, lambda: tag_test.tag_test_main("reset"))
            return
        
        self.progress_obj['value'] = 2
        self.progress_txt['text']= "Soak Tags"

        TEST_EVENT_QUEUE.append(self.after(1, lambda: tag_test.tag_test_main("energous pam cw 1")))
        TEST_EVENT_QUEUE.append(self.after(self.pStore.configParam["delays"]["maxPowerOffDelay"], self.test_tags_soak_off))

    def test_tags_helper(self):
        self.load_next_button.state(['!disabled'])
        global TEST_EVENT_QUEUE
        if STOP_TAG_TEST:
            self.after(1, lambda: tag_test.tag_test_main("reset"))
            return
        
        self.progress_obj['value'] = 1
        self.progress_txt['text']= "Reset TX"
        self.after(1, lambda: tag_test.tag_test_main("reset"))
        TEST_EVENT_QUEUE.append(self.after(self.pStore.configParam["delays"]["maxPowerOnDelay"], self.test_tags_soak_on))

class AddToQueueFrame(TestSetup):
    def __init__(self, parent, prev_entries=[]):
        super().__init__(parent)
        self.pStore = parent
        print(parent)
        self.greet_label.config(text="Scan Next Batch")

        # self.clear_button.grid_remove()
        self.load_next_button.grid_remove()
        self.login_button.grid_remove()
        self.oprtr_en_obj.grid_remove()
        self.shift_obj.grid_remove()
        self.start_button.config(width=25, text="Add to queue", command=self.add2q)

        queue_length = len([x for x in prev_entries if x.tagText.get() != ''])
        if queue_length > 0:
            self.start_button.state(['!disabled'])
            for i, tag in enumerate(prev_entries):
                cell_txt = tag.tagText.get()
                if cell_txt != '':
                    # self.tag_input_obj.insert(0, cell_txt)
                    self.tag_frames[i].tagText.set(cell_txt.upper()) 
                    self.tag_frames[i].tagObject.config(background='')
                    self.tag_frames[i].spotLabel.config(background='')
                    self.current_tag_cnt += 1

    def add2q(self):
        # print('added')
        self.pStore.destroy()

class ResultScreen(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, padding="3 3 12 12")

        self.pStore = parent

        self.greet_label = ttk.Label(self, text="Results")

        # self.retest_button = ttk.Button(self, width=25, text="Retest", command=self.retest_button_helper)
        self.done_button = ttk.Button(self, width=25, text="Done", command=self.done_button_helper)

        self.rb_query = " SELECT `serial_num` FROM `" + f"{db_model}_{db_table}" + "` WHERE `serial_num` = %s"

        for child in self.winfo_children():
            child.grid_configure(padx=5, pady=5)

        self.tag_frames = [0 for l in range(25)]

        let = ["A", "B", "C", "D", "E"]
        letNum = 0
        num = 1
        for fN in range(25):
            spotLabel = let[letNum]+str(num)
            self.tag_frames[fN] = ttk.Frame(self, relief='solid', borderwidth=5)
            self.tag_frames[fN].tagText = StringVar()
            self.tag_frames[fN].tagObject = ttk.Label(self.tag_frames[fN], background="black", width=25, anchor="center", textvariable=self.tag_frames[fN].tagText)
            self.tag_frames[fN].spotLabel = ttk.Label(self.tag_frames[fN], background="black", width=25, anchor="center", text=spotLabel)
            num += 1
            if num == 6:
                num = 1
                letNum += 1
        self.current_tag_cnt = 0

        # TODO: when testing is done, redo into loop
        self.columnconfigure(0, weight=100)
        self.columnconfigure(1, weight=1)
        self.columnconfigure(2, weight=1)
        self.columnconfigure(3, weight=1)
        self.columnconfigure(4, weight=1)
        self.columnconfigure(5, weight=1)
        self.columnconfigure(6, weight=100)

        
        self.rowconfigure(0, weight= 100)
        self.rowconfigure(1, weight=1)
        self.rowconfigure(2, weight=50)
        self.rowconfigure(3, weight=50)
        self.rowconfigure(4, weight=50)
        self.rowconfigure(5, weight=50)
        self.rowconfigure(6, weight=50)
        self.rowconfigure(7, weight=1)
        self.rowconfigure(8, weight=1)
        self.rowconfigure(9, weight=100)

        self.grid(column=0, row=0, sticky=(N, W, E, S))

        self.greet_label.grid(column=0, row=1, columnspan=7)
        rowCnt = 1
        for e in range(25):
            if(e%5 == 0):
                rowCnt += 1
            self.tag_frames[e].grid(column=(e%5)+1, row=rowCnt, sticky=(N, W, E, S))
            self.tag_frames[e].columnconfigure(0, weight=1)
            
            self.tag_frames[e].rowconfigure(0, weight= 1)
            self.tag_frames[e].rowconfigure(1, weight=1)

            self.tag_frames[e].tagObject.grid(column=0, row=0, sticky=(N, W, E, S))
            self.tag_frames[e].spotLabel.grid(column=0, row=1, sticky=(N, W, E, S))
        
        # self.retest_button.grid(column=1, row=8, sticky=(N, W, E, S))
        self.done_button.grid(column=5, row=8, sticky=(N, W, E, S))

        self.bind("<Map>", self.update_results)

    # def retest_button_helper(self):
    #     print("retest stub")

    def done_button_helper(self):
        print('--- remaining', tag_db_details)
        self.pStore.change_frame(TestSetup)

    def update_results(self, event):
        if test_mode == 'PRODUCTION':
            self._prod_mode(event)
        else:
            # self._dev_mode(event)
            self._debug_mode(event)

        for j in range(num_tags, 25):
            self.tag_frames[j].tagText.set("")
            self.tag_frames[j].tagObject.config(background="grey")
            self.tag_frames[j].spotLabel.config(background="grey")

    def _debug_mode(self, event):
        global result_list
        global tag_db_details

        db_conn = pymysql.connect(**db_config)
        cursor = db_conn.cursor(DictCursor)

        for i in range(num_tags):
            if STORE_TO_DB.get() == "1":
                self.tag_frames[i].tagText.set(tags_tested[i]["Board_Serial"])
            else:
                self.tag_frames[i].tagText.set(tags_tested[i]["ENID"])

            prod_id = self.tag_frames[i].tagText.get().upper()
            db_deets = tag_db_details.pop(prod_id)

            now = datetime.now()
            test_details = db_deets | login_details | {'date_time': now.isoformat(sep=' ', timespec='seconds')}

            try:
                if result_list[i] == 0:
                    self.tag_frames[i].tagObject.config(background="red")
                    self.tag_frames[i].spotLabel.config(background="red")
                    test_details['remarks'] =  f"POS{i} " + tags_tested[i]["Fail_Reason"]
                    test_details['status'] = 0
                else:
                    self.tag_frames[i].tagObject.config(background="lightgreen")
                    self.tag_frames[i].spotLabel.config(background="lightgreen")
                    test_details['status'] = 1
            except IndexError:
                pass

            print(test_details)
            if db_deets.get('test_rep', 0) > 1:
                table_name = f"`{db_model}_{db_table}`"
                serial_num = db_deets.get('serial_num')
                trep_query = " SELECT `test_rep` FROM " + table_name + " WHERE `serial_num` = %s "
                cursor.execute(trep_query, (serial_num,))
                last_rep = cursor.fetchone()['test_rep']
                print('last rep:', last_rep)

            curr_headers = list(test_details.keys())
            values = [f"%({head})s" for head in curr_headers]
            write_query = f" INSERT INTO `{db_model}_{db_table}` ({','.join(curr_headers)}) VALUES ({', '.join(values)})"
            print(write_query)

        cursor.close()
        db_conn.close()

    def _dev_mode(self, event):
        global result_list
                
        for i in range(num_tags):
            if STORE_TO_DB.get() == "1":
                self.tag_frames[i].tagText.set(tags_tested[i]["Board_Serial"])
            else:
                self.tag_frames[i].tagText.set(tags_tested[i]["ENID"])

            if result_list[i] == 0:
                self.tag_frames[i].tagObject.config(background="red")
                self.tag_frames[i].spotLabel.config(background="red")
            else:
                self.tag_frames[i].tagObject.config(background="lightgreen")
                self.tag_frames[i].spotLabel.config(background="lightgreen")

    def _prod_mode(self, event):
        global result_list
        global tag_db_details
        
        with pymysql.connect(**db_config) as db_conn:
            with db_conn.cursor(DictCursor) as cursor:
                for i in range(num_tags):
                    if STORE_TO_DB.get() == "1":
                        self.tag_frames[i].tagText.set(tags_tested[i]["Board_Serial"])
                    else:
                        self.tag_frames[i].tagText.set(tags_tested[i]["ENID"])

                    prod_id = self.tag_frames[i].tagText.get().upper()
                    try:
                        db_deets = tag_db_details.pop(prod_id)
                    except KeyError:
                        messagebox.showerror('Error', 'Unit has no details in Database')
                        continue
        
                    now = datetime.now()
                    test_details = db_deets | login_details | {'date_time': now.isoformat(sep=' ', timespec='seconds')}
                    
                    if result_list[i] == 0:
                        self.tag_frames[i].tagObject.config(background="red")
                        self.tag_frames[i].spotLabel.config(background="red")
                        test_details['remarks'] = f"POS{i} " + tags_tested[i]["Fail_Reason"]
                        test_details['status'] = 0
                    else:
                        self.tag_frames[i].tagObject.config(background="lightgreen")
                        self.tag_frames[i].spotLabel.config(background="lightgreen")
                        test_details['status'] = 1

                    if db_deets.get('test_rep', 0) > 1:
                        table_name = f"`{db_model}_{db_table}`"
                        serial_num = db_deets.get('serial_num')
                        trep_query = " SELECT `test_rep` FROM " + table_name + " WHERE `serial_num` = %s "
                        cursor.execute(trep_query, (serial_num,))
                        last_rep = cursor.fetchone()['test_rep']
                        print('last rep:', last_rep)
        
                        new_serial = f"{serial_num}_{last_rep}"
                        rw_query = " UPDATE "+ table_name + " SET `serial_num` = %s WHERE `serial_num` = %s "
                        cursor.execute(rw_query, (new_serial, serial_num))
                        db_conn.commit()

                    curr_headers = list(test_details.keys())
                    values = [f"%({head})s" for head in curr_headers]
                    write_query = f" INSERT INTO `{db_model}_{db_table}` ({','.join(curr_headers)}) VALUES ({', '.join(values)})"
                    print(write_query)

                    write_success = False
                    for i in range(3):
                        try:
                            cursor.execute(write_query, test_details)
                            db_conn.commit()

                            cursor.execute(self.rb_query, (test_details['serial_num'],))
                            resp = cursor.fetchone()
                            if resp:
                                write_success = True
                                break
                        except:
                            pass

                    if not write_success:
                        messagebox.showerror("Error", "Database write failed.")

class MenuBar(Menu):
    def __init__(self, parentWindow):
        super().__init__(parentWindow)
        self.pWin = parentWindow
        parentWindow['menu'] = self
        self.menu_tools = Menu(self)
        self.menu_options = Menu(self)
        self.add_cascade(menu=self.menu_options, label='Options')
        self.add_cascade(menu=self.menu_tools, label='Tools')

        self.menu_tools.add_command(label='Check Tag ID', command=self.testTag)

        self.menu_options_serialPort = Menu(self.menu_options)
        self.menu_options.add_cascade(menu=self.menu_options_serialPort, label='Set Serial Port...')
        self.menu_options_serialPort.add_command(label="Check For Ports", command=self.findSerialPorts)
        self.menu_options_serialPortOpts = []
        self.findSerialPorts()

        self.menu_options.add_checkbutton(label="Auto-Submit", variable=SCAN_WATCH, onvalue=1, offvalue=0)

        self.menu_options_enableDB = Menu(self.menu_options)
        self.menu_options.add_cascade(menu=self.menu_options_enableDB, label='MongoDB...')
        self.menu_options_enableDB.add_checkbutton(label='Use MongoDB', variable=STORE_TO_DB, onvalue="1", offvalue="0", command=lambda: self.pWin.event_generate("<<ToggleMongo>>"))

        self.menu_options_changeMode = Menu(self.menu_options)
        self.menu_options.add_cascade(menu=self.menu_options_changeMode, label='Change Mode...')
        self.mode = StringVar()
        self.menu_options_changeMode.add_radiobutton(label='Development', variable=self.mode, value='Development', command=self.modeChanged)
        self.menu_options_changeMode.add_radiobutton(label='Production', variable=self.mode, value='Production', command=self.modeChanged)
        self.mode.set('Development')

    def modeChanged(self):
        curr_mode = self.mode.get()
        print('Set to', curr_mode, 'Mode')
        self.pWin.frame.setMode(curr_mode)

    def testTag(self):
        self.tester_screen = TagIdCheck(self.pWin)
        self.tester_screen.minsize(250,150)
        self.tester_screen.protocol("WM_DELETE_WINDOW", self.dismissChecker) # intercept close button
        self.tester_screen.transient(self.pWin)   # dialog window is related to main
        self.tester_screen.wait_visibility() # can't grab until window appears, so we wait
        self.tester_screen.grab_set()        # ensure all input goes to our window
        self.tester_screen.wait_window()     # block until window is destroyed

    def dismissChecker(self):
        self.tester_screen.grab_release()
        self.tester_screen.destroy()

    def drawSerialPorts(self):
        self.menu_options_serialPort.add_command(label="Check For Ports", command=self.findSerialPorts)
        for p in self.menu_options_serialPortOpts:
            self.menu_options_serialPort.add_radiobutton(label=p, variable=tag_test.DEFAULT_SERIAL, value=p)

    def findSerialPorts(self):
        self.menu_options_serialPort.delete(0,"end")
        
        ports = serial.tools.list_ports.comports()
        valid_ports = []
        self.menu_options_serialPortOpts = []
        for port in ports:
            if port.description.startswith("USB Serial Port"): 
                valid_ports.append(port.device)

        for p in valid_ports:
            self.menu_options_serialPortOpts.append(p)

        self.drawSerialPorts()

class TagIdCheck(Toplevel):
    def __init__(self, parent):
        super().__init__()
        
        self.pStore = parent

        self.frame = TagIdCheckFrame(self)
        self.gui_setup()

    def gui_setup(self):
        self.title("Check Tag ID")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.frame.grid() 

class TagIdCheckFrame(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, padding="3 3 12 12")

        self.pStore = parent

        self.greet_label = ttk.Label(self, text="Scan Tag To Check ID")
        self.displayID_text = StringVar()
        self.displayID_label = ttk.Label(self, textvariable=self.displayID_text)
        self.tag_check_text = StringVar()
        self.tag_check_box = ttk.Entry(self, textvariable=self.tag_check_text, width=25)

        for child in self.winfo_children():
            child.grid_configure(padx=5, pady=5)

        self.grid(column=0, row=0, sticky=(N, W, E, S))

        # TODO: when testing is done, redo into loop
        self.columnconfigure(0, weight=100)
        self.columnconfigure(1, weight=1)
        self.columnconfigure(2, weight=100)

        self.rowconfigure(0, weight= 100)
        self.rowconfigure(1, weight=1)
        self.rowconfigure(2, weight=1)
        self.rowconfigure(3, weight=100)

        self.greet_label.grid(column=1, row=1)

        self.displayID_label.grid(column=1, row=2)

        self.tag_check_box.grid(column=1, row=3)
        self.tag_check_box.focus_set()

        
        self.tag_check_text.trace_add("write", self.scan_watch)

    def scan_watch(*args):
        if len(args[0].tag_check_text.get()) == REG_EX_LEN:
            args[0].scan_enter("<Return>") # TODO: verify
    
    def scan_enter(self, event): # TODO: how handle case for letters A-F
        # validate what is in the tag
        if bool(re.match(REG_EX, self.tag_check_text.get())):
            self.displayID_text.set(self.tag_check_text.get())
        else:
            #incorrect address
            messagebox.showerror(message="Invalid ID!", title="Invalid!")
        
        self.tag_check_box.delete(0, 'end')

def average_helper(arr): 
    arr_nums = [int(x) for x in arr if x != "0"]
    num = len(arr_nums)
    arr_nums.sort()
    arr_nums = arr_nums[(num//4):(((num*3)//4) + 1)]
    num = len(arr_nums)
    sum = 0
    for x in arr_nums:
        sum += x

    return round(sum/num, 2)

def ft_safe_exit(ret_code):
    tag_test.tag_test_main("reset")
    sys.exit(ret_code)


def ft_sig_handler(sig, frame):
    ft_safe_exit(130)

def main():
    signal.signal(signal.SIGINT, ft_sig_handler)
    root = EnEsnsTest()
    root.option_add('*tearOff', FALSE)
    root.minsize(800,500)
    menubar = MenuBar(root)
    root.protocol("WM_DELETE_WINDOW", root.dismissChecker)
    root.mainloop()

if __name__ == '__main__':
    main()