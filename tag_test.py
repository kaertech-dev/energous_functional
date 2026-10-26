import os
import sys
import signal
import serial

READ_SIZE = 4096
CMD_PREFIX = "! "
CMD_SUFFIX = "\r\n"

SERIAL_HANDLE = None
LOG_ENABLED = False

DONE_SEND = 0

DEFAULT_SERIAL = None


def send_cmd(sock, cmd, rsp_len):
    ''' Send Command '''
    try:
        # print(f"RawCmd: {cmd}")
        sock.write(cmd.encode('utf-8'))
        data = sock.read(rsp_len)
        # print(f"RawRsp: {data}")
        return data.decode()
    except Exception as error:
        raise ValueError(f"Write/Read failed {error}") from error


def safe_exit(ret_code):
    ''' Safely exit the function aftre cleaning up the resources'''
    global SERIAL_HANDLE
    # global LOG_ENABLED
    # if LOG_ENABLED:
    #     print("Disabling log...")
    #     cmd = f"{CMD_PREFIX}energous dbg 0{CMD_SUFFIX}"
    #     rsp = send_cmd(SERIAL_HANDLE, cmd, READ_SIZE)
    #     print(f"{rsp}")
    if SERIAL_HANDLE is not None:
        # print("Closing serial...")
        SERIAL_HANDLE.close()
    # os._exit(ret_code)


def sig_handler(sig, frame):
    ''' Signal Handler to force safe exit '''
    safe_exit(130)


def debug_log(sock):
    ''' Debug Log Messages to console '''
    global LOG_ENABLED
    LOG_ENABLED = True
    print("Enabling log...")
    cmd = f"{CMD_PREFIX}energous dbg 1{CMD_SUFFIX}"
    rsp = send_cmd(sock, cmd, READ_SIZE)
    print(f"{rsp}")
    while LOG_ENABLED:
        rsp = sock.read(READ_SIZE)
        if len(rsp) > 0:
            print(f"{rsp[1:].decode('utf-8')}", sep='')

def tag_test_main(inCmd):
    global DONE_SEND
    DONE_SEND = 0
    print(inCmd)
    signal.signal(signal.SIGINT, sig_handler)
    #TODO: handle the botton using the yaml file
    global SERIAL_HANDLE
    try:
        SERIAL_HANDLE = serial.Serial(
           f"{DEFAULT_SERIAL.get()}", 115200, timeout=0.5)
    except BaseException as err:
        print(f"\nFailed to open {DEFAULT_SERIAL.get()}")
        sys.exit(1)
    
    try:
        cmd = CMD_PREFIX + inCmd + CMD_SUFFIX
        rsp = send_cmd(SERIAL_HANDLE, cmd, READ_SIZE)
        print(f"{rsp}") # TODO: return this
    except ValueError as err:
        print(f"{inCmd} failed: {err}")

    safe_exit(0)

    DONE_SEND = 1
    try:
        return rsp
    except UnboundLocalError as err:
        print("BRG off")
        return ""


if __name__ == "__main__":
    print("helper only")
