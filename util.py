"""
Collection of util functions used by FrameSpace endpoint classes
"""

import ujson as json
from flask import request, make_response, jsonify
from google.protobuf import json_format
from bson import ObjectId
from api.exceptions import BadRequestException

def buildResponse(data):
  """
  Functionality that bypasses jsonify
  The try and except is temporarily here until
  the handling of NaN values is addressed 
  (ujson plays funny with these)
  """
  try:
    resp = make_response(json.dumps(data), 200)
    resp.content_type = 'application/json'
    return resp
  except:
    return jsonify(data)

def nullifyToken(json):
  if json.get('nextPageToken', None) is not None:
    json['nextPageToken'] = None
  return json

def toFlaskJson(protoObject):
  """
  Serialises a protobuf object as a flask Response object
  """
  js = json_format._MessageToJsonObject(protoObject, True)
  return buildResponse(nullifyToken(js))

def fromJson(json, protoClass):
  """
  Deserialise json into an instance of protobuf class
  """
  try:
    return json_format.Parse(json, protoClass())
  except Exception as e:
    raise BadRequestException(str(e))

def getMongoFieldFilter(filterList, maptype, from_get=False):

  # catch GET calls
  if from_get:
    filterList = filterList[0].split(',')

  try:
    return {"$in": map(maptype, filterList)}
  except:
    return None

def setMask(request_list, identifier, mask):

  if identifier in request_list:
    request_list.remove(identifier)
    return {mask: 0}
  return None

def getKeySpaceInfo(db, keyspace_id, mask=None):
  keyspace = db.keyspace.find_one({"_id": ObjectId(keyspace_id)}, mask)
  return keyspace['name'], keyspace.get('keys', [])

def getRequest(request, return_json={"names":[]}):
  """
  Helper method to handle empty jsons
  """
  if request.get_json() == {}:
    return return_json
  elif not request.json:
    return "Bad content type, must be application/json\n"

  return request.json

def authenticate(request):
  token = request.headers.get('authorization', None)
  return str(token)

