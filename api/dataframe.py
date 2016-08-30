from flask import request, jsonify
from flask_restful import Resource
import json
from bson import ObjectId

import util as util
from proto.framespace import framespace_pb2 as fs
from google.protobuf import json_format

class DataFrame(Resource):
  """
  API Resource that describes a dataframe slice.

  message SliceDataFrameRequest {
    string dataframe_id = 1;
    Dimension new_major = 2;
    Dimension new_minor = 3;
    int32 page_start = 4;
    int32 page_end = 5;
  }

  message DataFrame {
    string id = 1;
    Dimension major = 2;
    Dimension minor = 3;
    repeated Unit units = 4;
    map<string, string> metadata = 5;
    map<string, google.protobuf.Struct> contents = 6;
  }
  """

  def __init__(self, db):
    self.db = db

  def get(self, dataframe_id):
    """
    GET /dataframe/<dataframe_id>
    """
    d = {'dataframeId': dataframe_id}
    for arg in request.args:
      if arg[:4] == 'page':
        d[str(arg)] = int(request.args[arg][0])
      if arg[:3] == 'new':
        d[str(arg)] = {'keys': request.args[arg].split(',')}
    return self.sliceDataFrame(json.dumps(d))


  def post(self):
    """
    POST {"dataframeId": ID}
    Returns a dataframe or a subset of a dataframe. 
    Unsupported: Transpose via passing dimensions. 
    Speed up by by-passing proto message creation in response
    """
    if not request.json:
      return "Bad content type, must be application/json\n"

    if request.json.get('dataframeId', None) is None:
      return "dataframeId required for sliceDataframe.\n"

    return self.sliceDataFrame(json.dumps(request.json))

  def sliceDataFrame(self, request):

    try:

      # inits
      vec_filters = {}

      # validate request
      jreq = util.fromJson(request, fs.SliceDataFrameRequest)

      # first request to get dataframe
      result = self.db.dataframe.find_one({"_id": ObjectId(str(jreq.dataframe_id))})

      # prep vector query
      vc = result.get('contents', [])
      
      # save page end for later check
      page_end = int(jreq.page_end)
      # if page start is outside of dataframe length, return empty
      if jreq.page_start > len(vc):
        dataframe = {"id": str(result["_id"]), \
                   "major": {"keyspaceId": str(result['major']), "keys": []}, \
                   "minor": {"keyspaceId": str(result['minor']), "keys": []}, \
                   "contents": []}
        return jsonify(dataframe)

      elif jreq.page_end > len(vc) or len(jreq.new_minor.keys) > 0 or jreq.page_end == 0:
        jreq.page_end = len(vc)

      # construct vector filters
      vec_filters["_id"] = {"$in": vc[jreq.page_start:jreq.page_end]}

      kmaj_keys = None
      if len(jreq.new_major.keys) > 0:
        kmaj_keys = {"contents."+str(k):1 for k in jreq.new_major.keys}
        kmaj_keys['key'] = 1

      if len(jreq.new_minor.keys) > 0:
        vec_filters['key'] = {"$in": map(str, jreq.new_minor.keys)}

      # seconrd query to backend to get contents
      vectors = self.db.vector.find(vec_filters, kmaj_keys)
      vectors.batch_size(1000000)
      # construct response

      contents = {vector["key"]:vector["contents"] for vector in vectors}

      # avoid invalid keys passing through to keys
      # explore impacts on response time
      kmaj_keys = []
      if len(jreq.new_major.keys) > 0:
        kmaj_keys = contents[contents.keys()[0]].keys()
      # return keys in dimension, 
      # if the whole dimension is not returned
      kmin_keys = []
      # if len(jreq.new_minor.keys) > 0 or page_end < len(vc):
      if len(jreq.new_minor.keys) > 0 or page_end == 0:
        kmin_keys = contents.keys()

      dataframe = {"id": str(result["_id"]), \
                   "major": {"keyspaceId": str(result['major']), "keys": kmaj_keys}, \
                   "minor": {"keyspaceId": str(result['minor']), "keys": kmin_keys}, \
                   "contents": contents}

      return jsonify(dataframe)

    except Exception as e:
      return jsonify({500: str(e)})