import pymongo, os
from pymongo import MongoClient
import pandas as pd

class Connector:

  def __init__(self, database, host='0.0.0.0', port=27017):
    """
    Connect to specified database, and ensure proper setup.
    """
    self.conn = MongoClient(host, port, maxPoolSize=1000, serverSelectionTimeoutMS=300000)
    self.db = self.conn[database]
    self.port = port
    # check collections
    self.axis = self.db.axis
    self.keyspace = self.db.keyspace
    self.units = self.db.units
    self.vector = self.db.vector
    self.dataframe = self.db.dataframe

  def __enter__(self):
    return self

  def __exit__(self, exc_type, exc_value, traceback):
    # create indexes, where should this happen?
    self.keyspace = keyspace.create_index([{"keys", pymongo.ASCENDING}])
    self.dataframe = dataframe.create_index([{"contents": 1}])
    self.vector = vector.create_index([{"contents":1}])
    # reindex?
    self.conn.close()

  def registerAxes(self, axes):
    """
    Register any new axes secified in config. 
    """
    # first register available axes in config
    for axis in axes:
      self.axis.update({'name': axis['name']}, axis, upsert=True)

  

  def checkAxes(self, axis_name):
    """
    Check to make sure keyspace axes are actually in database.
    """
    ax = self.axis.find_one({'name': axis_name})
    if ax is None:
      raise ValueError("KeySpace Axis must be registered of specified in config axes section.")


  def registerUnits(self, units):
    """
    Register any newly specified units.
    Units is a required field in the config, so no checking is necessary.
    """
    registeredUnits = []
    for unit in units:
      u = self.units.find_and_modify({'name': unit['name']}, unit, upsert=True, full_response=True)
      try:
        # registered new unit
        _id = u['lastErrorObject']['upserted']
      except:
        # updated unit
        _id = u['value']['_id']

      registeredUnits.append(_id)
    return registeredUnits


  def registerKeyspaceFile(self, metadata, name, keys, axis):
    """
    Registration of keyspaces from a metadata file.
    Keyspaces are unique based on their name/axis_name pair
    """
    self.checkAxes(axis)

    with open(metadata) as meta:
      # construct a list of unique keyspaces
      m_df = pd.read_table(meta)
      kspaces = m_df[name].unique()

      # construct a dictionary of keyspaces for bulk insert
      keyspaces = []
      for ks in kspaces:
        ks_df = m_df[m_df[name].str.contains(ks)]
        key_list = list(ks_df[keys])
        ks_obj = {'name': ks.replace('.','-'), 'axis_name': axis, 'keys': key_list}
        self.keyspace.update({'name': ks, 'axis_name': axis}, ks_obj, upsert=True)
      del m_df


  def registerKeyspaceEmbedded(self, df, ksminor_id, ksminor_name, ksminor_axis, rename=None, keys=None, is_json=False):
    """
    Registers a keyspace that is embedded in a matrix, any filtering is assumed to have happened prior to registration.
    ie. ksminor_filter must occur on df before running minor ks registration.
    """
    # get keys
    if keys is None:
      if rename is None:
        keys = list(df[str(ksminor_name)])
      else:
        print 'rename flag set', rename
        if not is_json:
          keys = list(df[str(rename[ksminor_id])])
        else:
          keys = df['contents'].keys()

    # register minor keyspace
    minor_keyspace = {"name": ksminor_name, "axis_name": ksminor_axis, "keys": keys}
    min_ks = self.keyspace.update({"name": ksminor_name, "axis_name": ksminor_axis}, minor_keyspace, upsert=True)

    return min_ks.get("upserted", self.keyspace.find_one({"name": ksminor_name, "axis_name": ksminor_axis})['_id'])


  def registerDataFrame(self, df, ksminor_objid, units, is_json=False):
    """
    Gets respecitve major keyspace.
    Registers the lines of the tsv file as vectors.
    Register the tsv as a dataframe with pointer to vectors.
    """
    # get major keyspace
    # assumes all keys are registered
    if is_json:
      md_ks = self.keyspace.find_one({"keys": {"$regex": df['key']}})
      if md_ks is not None:
        jdf = self.dataframe.find_one({"major": md_ks['_id'], "minor": ksminor_objid, "units": units})
        vector = self.vector.insert_one(createVector(md_ks['_id'], ksminor_objid, units, df, is_json=True))
        if jdf is not None:
          ndf = self.dataframe.update({"_id":jdf["_id"]}, {"$push": {"contents": vector.inserted_id}})
          return ndf
        else:
          ndf = self.dataframe.insert_one({"major": md_ks['_id'], "minor": ksminor_objid, "units": units, "contents": [vector.inserted_id]})
          return ndf.inserted_id
      else:
        print "No keyspace belonging to the key {0}.".format([df['key']])

    else:
      keys = df.columns.tolist()[1:]
      md_ks = self.keyspace.find_one({"keys": {"$regex": keys[0]}})
      if md_ks is not None:
        # vectors are inserted into dataframe as ids to get around data storage limit
        vectors = self.vector.insert_many(map(createVectorClos(md_ks['_id'], ksminor_objid, units), df.reset_index().to_dict(orient='records')))
        dataframe = {"major": md_ks['_id'], "minor": ksminor_objid, "units": units, "contents": list(vectors.inserted_ids)}

        _id = self.dataframe.insert_one(dataframe)
        return _id
      else:
        raise ValueError("KeySpace must be registered before registering dataframe.")

def createVector(major, minor, units, vector, is_json=False):
  try:
    # get non-transposed vector
    key = vector.pop('key')
    del vector['index']
  except:
    # get transposed vector
    if not is_json:
      key = vector.pop('index')
  if is_json:
    del vector['expressionForEdges']
    del vector['gid']
    del vector['type']
    vector = vector['contents']

  return {'key': key, 'contents': vector, 'info':{}, 'majks': major, 'minks': minor, 'units':units}

def vectorFromCGD(vector, majks, units):
  pass

def createVectorClos(major, minor, units):
  def f(vector):
      return createVector(major, minor, units, vector)
  return f
