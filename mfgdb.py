"""Manufacturing Database Access Module"""

#pylint: disable=missing-docstring,too-many-arguments,unused-variable

import sys
from colorama import Fore, Style
import pymongo

import os
import yaml

MFG_DB_TIMEOUT_MS = 5000

MFG_DB_SERVER_HOST_DEFAULT = "169.254.116.232"
MFG_DB_SERVER_PORT_DEFAULT = 27017
MFG_DB_USER_DEFAULT = "enTest"
MFG_DB_PASSWORD_DEFAULT = "en2026"

MFG_DB_TAGS_PROG_DB_DEFAULT = "esenseTagsProgramming"
MFG_DB_TAGS_TEST_DB_DEFAULT = "esenseTagsTest"


class MfgDatabase:
    """Manages MongoDB database"""

    client = None

    def __init__(self, db_host, db_port, user, passwd) -> None:
        self.client = pymongo.MongoClient(
            db_host,
            db_port,
            username=user,
            password=passwd,
            connectTimeoutMS=MFG_DB_TIMEOUT_MS,
            socketTimeoutMS=MFG_DB_TIMEOUT_MS,
            serverSelectionTimeoutMS=MFG_DB_TIMEOUT_MS,
        )
        self.db = None

    def set_db(self, db_name):
        self.db = self.client[db_name]

    def delete(self, product, query):
        """Delete document from the product collection

        Args:
            product (string): Product name. Automatically typcast to lower case
            query (dict): Dictionary {'Board_SN': 'F005397'}

        Returns: True on Success; False on Failure
        """
        try:
            self.client.admin.command("ping")
            col = self.db[product.lower()]
            del_result = col.delete_many(query)
            print(f"Deleted {del_result.deleted_count} documents")
            return del_result.deleted_count > 0
        except pymongo.errors.ConnectionFailure:
            print("ERROR: Server not available")
        return False

    def insert(self, product, data):
        """Insert document to the product collection

        Args:
            product (string): Product name. Automatically typecast to lower case
            data (dict): Dictionary or list of dictionary

        Returns: True on Success; False on Failure
        """
        try:
            self.client.admin.command("ping")
            col = self.db[product.lower()]
            e = col.insert_many(data) if isinstance(data, list) else col.insert_one(data)
            return True
        except pymongo.errors.ConnectionFailure:
            return False
        return False

    def rename(self, product, old_name, new_name, search_query = None):
        '''Rename all the fields in the collection '''
        col = self.db[product.lower()]
        try:
            result = col.update_many(search_query if search_query else {},
                                     {"$rename": {old_name: new_name}}).raw_result
            return result["nModified"] > 0
        except pymongo.errors.PyMongoError as e:
            print(e)
            return False

    def rename_collection(self, old_product, new_product):
        '''Rename the collection '''
        col = self.db[old_product.lower()]
        try:
            print('before rename', self.db.list_collection_names())
            col.rename(new_product.lower(), dropTarget = False)
            print('after rename', self.db.list_collection_names())
            return True
        except pymongo.errors.PyMongoError as e:
            print(e)
            return False

    def print_product_data(self, product, field=None):
        col = self.db[product.lower()]
        for x in col.find():
            if field:
                print(x[field])
            else:
                print(x)

    def update_product_data(self, product, search_query, update_query):
        col = self.db[product.lower()]
        newvalues = {"$set": update_query}
        try:
            result = col.update_many(search_query, newvalues).raw_result
            return result["nModified"] > 0
        except pymongo.errors.PyMongoError as e:
            print(e)
            return False

    def __find_without_duplicate(self, product, query, query_value, field, notfound_string, duplicate_string):
        col = self.db[product.lower()]
        # Count the number of rows
        doc_cnt = col.count_documents(query)
        if doc_cnt == 0:
            print(f"{notfound_string}: {query_value}")
            return None

        # Get the documents
        doc = col.find(query)
        # Check for duplicates System_SN with different Board_SN
        entries = []
        for row in doc:
            val = row[field].upper()
            if val not in entries:
                entries.append(val)
        if len(entries) > 1:
            print(f"{duplicate_string} - {entries}")
            return None
        return entries[0]

    def find_matching(self, product, query):
        col = self.db[product.lower()]
        # Get the documents
        return col.find(query)

    # def get_board_sn_from_system_sn(self, product, system_sn):

    #     board_sn = self.get_assembly_db_field(product, "System_SN", system_sn, "Board_SN")
    #     return board_sn

    # def get_assembly_db_field(self, product, input_name, input_val, field_name):
    #     """Get the field from the assembly db"""
    #     curr_db = self.db
    #     # Switch to assembly DB
    #     self.set_db(MFG_DB_ASSEMBLY_DB_DEFAULT)
    #     query = {input_name: input_val}
    #     field_val = self.__find_without_duplicate(
    #         product,
    #         query,
    #         input_val,
    #         field_name,
    #         f"No assembly entry found for {input_name}",
    #         f"Different Assembly info for same {input_name}: {input_val}",
    #     )
    #     # Restore the db
    #     self.db = curr_db
    #     return field_val.strip() if field_val else None

    # def get_bdaddress_from_board_sn(self, product, board_sn):
    #     bd_addr = None
    #     # Store the current db
    #     curr_db = self.db
    #     # Use MongoDB aggregation to retrieve 12 digit only unique ID.
    #     result = self.client[MFG_DB_PRIMARY_DB_DEFAULT][product].aggregate(
    #         [
    #             {
    #                 "$match": {
    #                     "Board_SN": {"$eq": board_sn},
    #                     "Serial Number": {"$exists": True},
    #                     "$expr": {"$eq": [{"$strLenCP": "$Serial Number"}, 12]},
    #                 }
    #             },
    #             {
    #                 "$group": {
    #                     "_id": {"Board_SN": "$Board_SN"},
    #                     "Serial Number": {"$addToSet": "$Serial Number"},
    #                     "count": {"$sum": 1},
    #                 }
    #             },
    #         ]
    #     )
    #     board_list = list(result)
    #     # It should have only one entry.
    #     if len(board_list) == 1:
    #         # Board list will be of below format and return first element
    #         # [{'_id': {'Board_SN': 'F005397'}, 'Serial Number': ['bd964e828024', "BD964e828024"], 'count': 2}]
    #         # Find different BD Address for same serial number exist
    #         serial_lst = board_list[0]["Serial Number"]
    #         upper_lst = [x.upper() for x in serial_lst]
    #         if len(upper_lst) == 1:
    #             bd_addr = upper_lst[0]
    #         else:
    #             print(
    #                 f"\nMultiple PT entries found for Board_SN: {Fore.YELLOW}{board_sn}{Style.RESET_ALL}"
    #             )
    #             print(
    #                 f"\tWith BD Addresses - {Fore.YELLOW}{upper_lst}{Style.RESET_ALL}"
    #             )
    #     else:
    #         print(
    #             f"No PT Data available for Board_SN: {Fore.YELLOW}{board_sn}{Style.RESET_ALL}"
    #         )
    #     # Restore the db
    #     self.db = curr_db
    #     return bd_addr

    # def get_bdaddress_from_system_sn(self, product, system_sn):
    #     bd_addr = None
    #     board_sn = self.get_board_sn_from_system_sn(product, system_sn)
    #     if board_sn:
    #         bd_addr = self.get_bdaddress_from_board_sn(product, board_sn)
    #     else:
    #         print(f"Board_SN not found for {Fore.YELLOW}{system_sn}{Style.RESET_ALL}")
    #     return bd_addr

    # def get_system_sn_from_bdaddress(self, product, bd_addr):
    #     """Get System_SN from BD Address"""
    #     # Store the current db
    #     curr_db = self.db
    #     # Switch to primary DB
    #     self.set_db(MFG_DB_PRIMARY_DB_DEFAULT)
    #     query = {"Serial Number": bd_addr}
    #     board_sn = self.__find_without_duplicate(
    #         product,
    #         query,
    #         bd_addr,
    #         "Board_SN",
    #         "No PT entry found for BD Address",
    #         f"Different PT info for same BD Address: {bd_addr}",
    #     )
    #     system_sn = self.get_assembly_db_field(product, "Board_SN", board_sn, "System_SN")
    #     # Restore the db
    #     self.db = curr_db
    #     return system_sn

    def close(self):
        self.client.close()
        self.client = None

def is_db_up(db_info):
    db_obj = get_db_obj(db_info, MFG_DB_TAGS_PROG_DB_DEFAULT)
    try:
        # The ping command is cheap and does not require auth
        db_obj.client.admin.command('ping')
    except pymongo.errors.ConnectionFailure:
        return False
    
    return True


def write_final_data_to_db(db_info, data):
    """Write the data into the final database

    Args:
        db_info (dictionary): Database information { "host" : "", "port" : No,
                                                     "user": "", "password":"" ,
                                                     "product" : "" }
        data (dictionary): Data to be written

    Returns: True on Success; False on Failure
    """
    enid = True
    system_sn = data.get("Board_Serial", None)
    if not system_sn:
        return "N/A"

    db_obj = get_db_obj(db_info, MFG_DB_TAGS_TEST_DB_DEFAULT)

    product = db_info.get("product", "UNSPECIFIED")
    
    status = db_obj.insert(product, data)
    if not status:
        enid = False

    db_obj.close()
    return enid

def write_db(test_result, station, db_cfg):
    """Writes the data into the database if configured

    Args:
        test_result (dict): Test result dictionaty
        equip_setup (dict): Configuration
    """

    test_result.update({"Station": station})
    return write_final_data_to_db(db_cfg, test_result)

def get_bdaddress_from_board_sn(db_info, product, board_sn):
    bd_addr = "N/A"
    # Store the current db
    db_obj = get_db_obj(db_info, MFG_DB_TAGS_PROG_DB_DEFAULT)
    # Use MongoDB aggregation to retrieve 12 digit only unique ID.
    result = db_obj.client[MFG_DB_TAGS_PROG_DB_DEFAULT][product].aggregate(
        [
                {
                    "$match": {
                        "Board_Serial": {"$eq": board_sn},
                        "BD_Address": {"$exists": True},
                        "$expr": {"$eq": [{"$strLenCP": "$BD_Address"}, 12]},
                    }
                },
                {
                    "$group": {
                        "_id": {"Board_Serial": "$Board_Serial"},
                        "BD_Address": {"$addToSet": "$BD_Address"},
                        "count": {"$sum": 1},
                    }
                },
            ]
    )
    board_list = list(result)
    # It should have only one entry.
    if len(board_list) == 1:
        # Board list will be of below format and return first element
        # [{'_id': {'Board_SN': 'F005397'}, 'Serial Number': ['bd964e828024', "BD964e828024"], 'count': 2}]
        # Find different BD Address for same serial number exist
        serial_lst = board_list[0]["BD_Address"]
        upper_lst = [x.upper() for x in serial_lst]
        if len(upper_lst) == 1: #TODO: how to handle?
            bd_addr = upper_lst[0]
        else:
            bd_addr = "DUPE"
        #     print(
        #         "\nMultiple PT entries found for Board_SN:", board_sn
        #     )
        #     print(
        #         "\tWith BD Addresses - ", upper_lst
        #     )
    else:
        bd_addr = "ND"
        # print(
        #     "No PT Data available for Board_SN: ", board_sn
        # )
    
    db_obj.close()
    return bd_addr

def get_enid_from_board_sn(db_info, product, board_sn):
    enid = "N/A"
    # Store the current db
    db_obj = get_db_obj(db_info, MFG_DB_TAGS_PROG_DB_DEFAULT)
    # Use MongoDB aggregation to retrieve 12 digit only unique ID.
    result = db_obj.client[MFG_DB_TAGS_PROG_DB_DEFAULT][product].aggregate(
        [
                {
                    "$match": {
                        "Board_Serial": {"$eq": board_sn},
                        "ENID": {"$exists": True},
                        "$expr": {"$eq": [{"$strLenCP": "$ENID"}, 8]},
                    }
                },
                {
                    "$group": {
                        "_id": {"Board_Serial": "$Board_Serial"},
                        "ENID": {"$addToSet": "$ENID"},
                        "count": {"$sum": 1},
                    }
                },
            ]
    )
    board_list = list(result)
    # It should have only one entry.
    if len(board_list) == 1:
        # Board list will be of below format and return first element
        # Find different BD Address for same serial number exist
        serial_lst = board_list[0]["ENID"]
        upper_lst = [x.upper() for x in serial_lst]
        if len(upper_lst) == 1: #TODO: how to handle?
            enid = upper_lst[0]
        else:
            bd_addr = "DUPE"
            # print(
            #     "\nMultiple PT entries found for Board_SN:", board_sn
            # )
            # print(
            #     "\tWith BD Addresses - ", upper_lst
            # )
    else:
        bd_addr = "ND"
        # print(
        #     "No PT Data available for Board_SN: ", board_sn
        # )
    
    db_obj.close()
    return enid

def get_db_obj(db_info, db_name):
    """Get the database object based on db_info"""
    db_host = db_info.get("host", "localhost")
    db_port = db_info.get("port", 27017)
    db_user = db_info.get("user", "mfgscript")
    db_passwd = db_info.get("password", "")
    db_obj = MfgDatabase(db_host, db_port, db_user, db_passwd)
    db_obj.set_db(db_name)
    return db_obj


# if __name__ == '__main__':
    # # dummyData = {"Board_Serial": "K22460490000", "BD_Address": "099E6A5232F7", "ENID": "00000012"}
    # # dummyData = {"Board_Serial": "K22460490235", "BD_Address": "34C0EA0742D1", "ENID": "00000000"}
    # # dummyData = {"Board_Serial": "K11111111111", "BD_Address": "0123456789AB", "ENID": "12345678"}
    # DB_CONFIG_FILE = os.path.join("config", "db.yaml")
    # with open(DB_CONFIG_FILE, encoding="utf-8") as dbFile:
    #     dbInfo = yaml.safe_load(dbFile)

    # db_obj = get_db_obj(dbInfo, MFG_DB_TAGS_PROG_DB_DEFAULT)

    # product = dbInfo.get("product", "UNSPECIFIED")
    # status = db_obj.insert(product, dummyData)
    # if not status:
    #     print(f"Error: Failed to insert into {product} database")
    #     bdaddr = None
    # else:
    #     print("Done: ", status)
    # db_obj.close()