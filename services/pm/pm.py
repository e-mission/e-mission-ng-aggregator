import json
# To support dynamic loading of client-specific libraries
import socket
import requests

from pymongo import MongoClient
import pymongo
import sys
from importlib import import_module
import bson
from shared_apis.bottle import route, post, get, run, template, static_file, request, app, HTTPError, abort, BaseRequest, JSONPlugin, response
from conf.machine_configs import machines_use_tls, upc_port

# Inspired by https://stackoverflow.com/questions/16586180/typeerror-objectid-is-not-json-serializable
def convert_string_to_objectid(dict_or_list_or_item):
    if isinstance(dict_or_list_or_item, dict):
        for key, value in dict_or_list_or_item.copy().items():
            # Agressively assume anything that can be an ObjectId is
            # This may cause us problems later
            if bson.ObjectId.is_valid(value):
                dict_or_list_or_item[key] = bson.ObjectId(value)
            else:
                convert_string_to_objectid(value)
    elif isinstance(dict_or_list_or_item, list):
        for item in dict_or_list_or_item:
            convert_string_to_objectid(item)

def convert_objectid_to_string(dict_or_list_or_item):
    if isinstance(dict_or_list_or_item, dict):
        for key, value in dict_or_list_or_item.copy().items():
            if isinstance(value, bson.ObjectId):
                dict_or_list_or_item[key] = str(value)
            else:
                convert_objectid_to_string(value)

    elif isinstance(dict_or_list_or_item, list):
        for i, value in enumerate(dict_or_list_or_item.copy()):
            if isinstance(value, bson.ObjectId):
                dict_or_list_or_item[i] = str(value)
            else:
                convert_objectid_to_string(value)


BaseRequest.MEMFILE_MAX = 1024 * 1024 * 1024 # Allow the request size to be 1G
# to accomodate large section sizes
app = app()

enc_key = None
mongoHostPort = 27017
url = "localhost"
databases = dict()

def _get_current_db(database_name):
    if database_name not in databases:
        databases[database_name] = MongoClient(host=url, port=mongoHostPort)[database_name]
    return databases[database_name]

def get_collection(database_name, collection_name, indices=None):
    collection = _get_current_db(database_name)[collection_name]
    if indices is not None:
        for index, elements in indices.items():
            # Should add checks for typing
            index_parts = index.split("\n")
            data_types = elements[0]
            assert(len(index_parts) == len(data_types))
            index_pairs = [(index_parts[i], data_types[0]) for i in range(len(index_parts))]
            is_sparse = elements[1]
            collection.create_index(index_pairs, sparse=is_sparse)
    return collection

def setInitPrivacyBudget():
    # Replace this with a sensible value.
    starting_budget = 1.0 
    setPrivacyBudget(starting_budget)
    return starting_budget

def setPrivacyBudget(budget):
    table = get_collection("Stage_PrivacyBudget" ,"privacyBudget")
    # We simply want to update everything so we make the query parameter empty
    query = dict()
    budget_dict = {"$set" : {"privacy_budget" : budget}}
    # Use update one because there should ever only be one document
    result = table.update_one(query, budget_dict, upsert=True)

def getPrivacyBudget():
    table = get_collection("Stage_PrivacyBudget" ,"privacyBudget")
    filtered = {"_id": False}
    storedBudget = table.find_one({}, filtered)
    if storedBudget is None:
        return setInitPrivacyBudget()
    else:
        return storedBudget["privacy_budget"]

def getCursor(find_method):
  
  # find arguments
  filter = request.json['filter']
  convert_string_to_objectid(filter)
  projection = request.json['projection']
  skip = request.json['skip']
  limit = request.json['limit']
  no_cursor_timeout = request.json['no_cursor_timeout']
  cursor_type = request.json['cursor_type']
  sort = request.json['sort']
  allow_partial_results = request.json['allow_partial_results']
  oplog_replay = request.json['oplog_replay']
  modifiers = request.json['modifiers']
  batch_size = request.json['batch_size']
  manipulate = request.json['manipulate']
  collation = request.json['collation']
  hint = request.json['hint']
  max_scan = request.json['max_scan']
  max_time_ms = request.json['max_time_ms']
  max = request.json['max']
  min = request.json['min']
  return_key = request.json['return_key']
  show_record_id = request.json['show_record_id']
  snapshot = request.json['snapshot']
  comment = request.json['comment']
  return find_method(filter, projection, skip, limit, no_cursor_timeout, 
          cursor_type, sort, allow_partial_results, oplog_replay, modifiers,
          batch_size, manipulate, collation, hint, max_scan, max_time_ms,
          max, min, return_key, show_record_id, snapshot, comment)

@post('/data/find_one')
def findOneData():
  if enc_key is None:
      abort (403, "Cannot load data without a key.\n") 
  database = request.json['database']
  collection = request.json['collection']
  # Indices is a json dict mapping keys to [data_type, is_sparse]
  # Each index is of the form itemA.itemB.....itemZ,
  indices = request.json['indices']
  

  db = get_collection(database, collection, indices)
  data = getCursor(db.find_one)
  result_dict = {'data' : data}
  convert_objectid_to_string(result_dict)
  return result_dict

@post('/data/find')
def findData():
  if enc_key is None:
      abort (403, "Cannot load data without a key.\n") 
  database = request.json['database']
  collection = request.json['collection']
  # Indices is a json dict mapping keys to [data_type, is_sparse]
  # Each index is of the form itemA.itemB.....itemZ,
  indices = request.json['indices']

  db = get_collection(database, collection, indices)

  cursor = getCursor(db.find)
  data = list(cursor)
  result_dict = {'data' : data}
  convert_objectid_to_string(result_dict)
  return result_dict

@post('/data/count')
def countData():
  if enc_key is None:
      abort (403, "Cannot load data without a key.\n")
  database = request.json['database']
  collection = request.json['collection']
  # Indices is a json dict mapping keys to [data_type, is_sparse]
  # Each index is of the form itemA.itemB.....itemZ,
  indices = request.json['indices']

  db = get_collection(database, collection, indices)

  cursor = getCursor(db.find)
  with_limit_and_skip = request.json['with_limit_and_skip']
  return {'count' : cursor.count(with_limit_and_skip)}

@post('/data/distinct')
def distinctData():
  if enc_key is None:
      abort (403, "Cannot load data without a key.\n")
  database = request.json['database']
  collection = request.json['collection']
  # Indices is a json dict mapping keys to [data_type, is_sparse]
  # Each index is of the form itemA.itemB.....itemZ,
  indices = request.json['indices']

  db = get_collection(database, collection, indices)

  cursor = getCursor(db.find)
  distinct_key = request.json['distinct_key']
  return {'distinct' : cursor.distinct(distinct_key)}

@post('/data/insert')
def insertData():
  if enc_key is None:
      abort (403, "Cannot store data without a key.\n") 
  database = request.json['database']
  collection = request.json['collection']
  # Data is the data transferred
  data = request.json['data']
  convert_string_to_objectid(data)
  # Indices is a json dict mapping keys to [data_type, is_sparse]
  # Each index is of the form itemA.itemB.....itemZ,
  indices = request.json['indices']

  is_many = request.json['is_many']
  # Get the database
  db = get_collection(database, collection, indices)
  bypass_document_validation = request.json['bypass_document_validation']
  result_dict = dict()
  if is_many:
    ordered = request.json['ordered']
    result = db.insert_many(data, ordered, bypass_document_validation)
    result_dict['inserted_ids'] = result.inserted_ids
  else:
    result = db.insert_one(data, bypass_document_validation)
    result_dict['inserted_id'] = result.inserted_id
  result_dict['acknowledged'] = result.acknowledged
  convert_objectid_to_string(result_dict)
  return result_dict

@post('/data/insert-deprecated')
def insertDepricatedData():
  if enc_key is None:
      abort (403, "Cannot store data without a key.\n") 
  database = request.json['database']
  collection = request.json['collection']
  # Indices is a json dict mapping keys to [data_type, is_sparse]
  # Each index is of the form itemA.itemB.....itemZ,
  indices = request.json['indices']
  # Get the database
  db = get_collection(database, collection, indices)

  # Get fields
  doc_or_docs = request.json['doc_or_docs']
  convert_string_to_objectid(doc_or_docs)
  manipulate = request.json['manipulate']
  check_keys = request.json['check_keys']
  continue_on_error = request.json['continue_on_error']
  # kwargs
  kwargs_dict = dict()
  if 'w' in request.json:
    kwargs_dict['w'] = request.json['w']
  if 'wtimeout' in request.json:
    kwargs_dict['wtimeout'] = request.json['wtimeout']
  if 'j' in request.json:
    kwargs_dict['j'] = request.json['j']
  if 'fsync' in request.json:
    kwargs_dict['fsync'] = request.json['fsync']

  result = db.insert(doc_or_docs, manipulate, check_keys,
          continue_on_error, **kwargs_dict)

  result_dict = {'resp': result}
  convert_objectid_to_string(result_dict)
  return result_dict

@post('/data/update')
def updateData():
  if enc_key is None:
      abort (403, "Cannot store data without a key.\n") 
  database = request.json['database']
  collection = request.json['collection']
  # query is the filter
  query = request.json['query']
  convert_string_to_objectid(query)
  # Data is the data transferred
  data = request.json['data']
  convert_string_to_objectid(data)
  # Indices is a json dict mapping keys to [data_type, is_sparse]
  # Each index is of the form itemA.itemB.....itemZ,
  indices = request.json['indices']
  is_many = request.json['is_many']
  upsert = request.json['upsert']
  bypass_document_validation = request.json['bypass_document_validation']
  collation = request.json['collation']
  # Get the database
  db = get_collection(database, collection, indices)
  if is_many:
    result = db.update_many(query, data, upsert=upsert, 
                bypass_document_validation=bypass_document_validation,
                collation=collation)
  else:
    result = db.update_one(query, data,upsert=upsert, 
                bypass_document_validation=bypass_document_validation,
                collation=collation)
  result_dict = dict()
  result_dict['acknowledged'] = result.acknowledged
  result_dict['matched_count'] = result.matched_count
  result_dict['modified_count'] = result.modified_count
  result_dict['raw_result'] = result.raw_result
  result_dict['upserted_id'] = result.upserted_id
  convert_objectid_to_string(result_dict)
  return result_dict

@post('/data/replace_one')
def replaceOneData():
  if enc_key is None:
      abort (403, "Cannot store data without a key.\n") 
  database = request.json['database']
  collection = request.json['collection']
  # query is the filter
  query = request.json['query']
  convert_string_to_objectid(query)
  # Data is the data transferred
  data = request.json['data']
  convert_string_to_objectid(data)
  # Indices is a json dict mapping keys to [data_type, is_sparse]
  # Each index is of the form itemA.itemB.....itemZ,
  indices = request.json['indices']
  upsert = request.json['upsert']
  bypass_document_validation = request.json['bypass_document_validation']
  collation = request.json['collation']
  # Get the database
  db = get_collection(database, collection, indices)
  result = db.replace_one(query, data, upsert=upsert, 
                bypass_document_validation=bypass_document_validation,
                collation=collation)

  result_dict = dict()
  result_dict['acknowledged'] = result.acknowledged
  result_dict['matched_count'] = result.matched_count
  result_dict['modified_count'] = result.modified_count
  result_dict['raw_result'] = result.raw_result
  result_dict['upserted_id'] = result.upserted_id
  convert_objectid_to_string(result_dict)
  return result_dict

@post('/data/update-deprecated')
def updateDepricatedData():
  if enc_key is None:
      abort (403, "Cannot store data without a key.\n") 
  database = request.json['database']
  collection = request.json['collection']
  # Indices is a json dict mapping keys to [data_type, is_sparse]
  # Each index is of the form itemA.itemB.....itemZ,
  indices = request.json['indices']
  # Get the database
  db = get_collection(database, collection, indices)

  # Get fields
  spec = request.json['spec']
  document = request.json['document']
  convert_string_to_objectid(document)
  upsert = request.json['upsert']
  manipulate = request.json['manipulate']
  check_keys = request.json['check_keys']
  # kwargs
  kwargs_dict = dict()
  
  if 'multi' in request.json:
    kwargs_dict['multi'] = request.json['multi']
  if 'w' in request.json:
    kwargs_dict['w'] = request.json['w']
  if 'wtimeout' in request.json:
    kwargs_dict['wtimeout'] = request.json['wtimeout']
  if 'j' in request.json:
    kwargs_dict['j'] = request.json['j']
  if 'fsync' in request.json:
    kwargs_dict['fsync'] = request.json['fsync']

  result = db.update(spec, document, upsert, manipulate, check_keys, **kwargs_dict)

  result_dict = {'resp': result}

  convert_objectid_to_string(result_dict)
  return result_dict

@post('/data/delete')
def deleteData():
  if enc_key is None:
      abort (403, "Cannot store data without a key.\n") 
  database = request.json['database']
  collection = request.json['collection']
  # query is the filter
  query = request.json['query']
  convert_string_to_objectid(query)
  # Indices is a json dict mapping keys to [data_type, is_sparse]
  # Each index is of the form itemA.itemB.....itemZ,
  indices = request.json['indices']
  is_many = request.json['is_many']
  # Get the database
  db = get_collection(database, collection, indices)
  collation = request.json['collation']
  if is_many:
    result = db.delete_many(query, collation)
  else:
    result = db.delete_one(query, collation)
  result_dict = dict()
  result_dict['acknowledged'] = result.acknowledged
  result_dict['deleted_count'] = result.deleted_count
  result_dict['raw_result'] = result.raw_result
  convert_objectid_to_string(result_dict)
  return result_dict

# Function used to deduct from the privacy budget. Returns
# whether or not it was possible to reduce the privacy budget.
@post ("/privacy_budget")
def reduce_privacy_budget():
    budget = getPrivacyBudget()
    cost = float(request.json['privacy_cost'])
    # Remove returning the budget after testing
    if budget - cost < 0:
        return {"success": False}
    else:
        budget -= cost
        setPrivacyBudget(budget)
        return {"success": True}


@post ("/cloud/key")
def add_encrypt_key():
    global enc_key
    if enc_key:
        abort (403, "Key already given\n")
    else:
        enc_key = request.json['key']
        bytes_str = bytes(enc_key, 'utf-8')
        if len(bytes_str) < 32:
            bytes_str = bytes_str + bytes("".join(['0'] * (32 - len(bytes_str))) , "utf-8")
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((url, 27018))
            # Send the first 32 bytes
            s.sendall (bytes_str[:32])
            s.recv(1024)

# Future work may also include adding permission checks here.

if __name__ == '__main__':
    # To avoid config file for tests
    server_host = socket.gethostbyname(socket.gethostname())
    # The selection of SSL versus non-SSL should really be done through a config
    # option and not through editing source code, so let's make this keyed off the
    # port number
    if machines_use_tls:
      # We support SSL and want to use it
      key_file = open('conf/net/keys.json')
      key_data = json.load(key_file)
      host_cert = key_data["host_certificate"]
      chain_cert = key_data["chain_certificate"]
      private_key = key_data["private_key"]

      run(host=server_host, port=upc_port, server='cheroot', debug=True,
          certfile=host_cert, chainfile=chain_cert, keyfile=private_key)
    else:
      # Non SSL option for testing on localhost
      print("Running with HTTPS turned OFF - use a reverse proxy on production")
      run(host=server_host, port=upc_port, server='cheroot', debug=True)

