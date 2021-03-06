import argparse, traceback, sys
from multiprocessing import Pool

import pandas as pd

from configreader import ConfigReader
from connector import Connector

class Importer:

  def __init__(self, config, files=[None], host='0.0.0.0', port=27017, is_json=False):
    """
    Importer will setup config and perform parallel import of tsv files into mongo.
    """

    if len(files) == 0 or type(files) is not list:
      raise ValueError("List of one of more tsv files required for import.")
    
    self.config = ConfigReader(config)
    init_file = files[0]
    tsv_files = files[1:]

    self.conn = Connector(self.config.db_name, host=host, port=port)

    if self.config.axes is not None:
      self.conn.registerAxes(self.config.axes)

    if self.config.ksf_map is not None:
      self.conn.registerKeyspaceFile(self.config.ksf_file, self.config.ksf_name, self.config.ksf_keys, self.config.ksf_axis)

    # register the first file to establish minor keyspace
    # allow registeration of keyspaces only
    if init_file is not None:
      # replace minor keyspace in tsv identifier with ksminor name
      # fix this later
      self.rename = {self.config.ksemb_id: 'key'}
      if is_json:
        with open(init_file) as j:
          import json, re
          dfs = [json.loads(re.sub(self.config.ksemb_id, 'contents', re.sub('barcode', self.rename[self.config.ksemb_id], str(line), 1), 1)) for line in j]
          init_df = dfs[0]
          tsv_files = dfs[1:]
          del dfs

      else:
        init_df = getDataFrame(init_file, ksminor_filter=self.config.ksemb_filter, ksminor_id=self.config.ksemb_id, rename=self.rename, transpose=self.config.transpose)
        
      ksmin_keys = None
      if self.config.infer_units:
        ksmin_keys = list(init_df.index)
        units = [{"name": i, "description":""} for i in ksmin_keys]
        self.config.units = units

      units = self.conn.registerUnits(self.config.units)

      self.minor_keyspaceId = self.conn.registerKeyspaceEmbedded(init_df, self.config.ksemb_id, self.config.ksemb_name, self.config.ksemb_axis, rename=self.rename, keys=ksmin_keys, is_json=is_json)

      # construct first dataframe and add to list to be registered
      try:
        self.conn.registerDataFrame(init_df, self.minor_keyspaceId, units, is_json=is_json)
        print "Completed: {0}".format(init_file)
      
      except Exception, e:
        traceback.print_exc(file=sys.stdout)
        print str(e)

      # work on the rest at once
      if len(tsv_files) > 0:
        parallelGen(tsv_files, self.minor_keyspaceId, units, self.config.db_name, self.config.ksemb_filter, self.config.ksemb_id, self.rename, host, port, is_json=is_json)

def poolLoadTSV((tsv, ks_minor, units, db, ksm_filter, ksm_id, rename, host, port, is_json)):
  """
  This function is used by multiprocess.Pool to populate framespace with a new dataframe.
  """
  try:
    # register vectors and get the dataframe object for insert
    conn = Connector(db, host=host, port=port)
    if is_json:
      df_id = conn.registerDataFrame(tsv, ks_minor, units, is_json=is_json)
    else:
      df_id = conn.registerDataFrame(getDataFrame(tsv, ksminor_id=ksm_id, ksminor_filter=ksm_filter, rename=rename), ks_minor, units)
  
  except Exception, e:
    traceback.print_exc(file=sys.stdout)

    print "Error processing"
    print str(e)
    return (-1, tsv)
  return (0, tsv)

def parallelGen(tsv_files, ks_minor, units, db, ksm_filter, ksm_id, rename, host, port, is_json):
  """
  Function that spawns the Pool of vector registration and dataframe production
  """

  function_args = [None] * len(tsv_files)
  index = 0
  for tsv in tsv_files:
    function_args[index] = (tsv, ks_minor, units, db, ksm_filter, ksm_id, rename, host, port, is_json)
    index += 1

  pool = Pool()
  failed = list()
  for returncode in pool.imap_unordered(poolLoadTSV, function_args):
    if returncode[0] == -1:
      failed.append(returncode[1])
    # else:
    #   # print "Completed: {0}".format(returncode[1])
    #   print "Completed"
  pool.close()
  pool.join()
  if len(failed):
    print "\nERROR: some data failed to process."
    # for f in failed:
    #   print "\t{0}".format(f)
    # raise Exception("Execution failed on {0}".format(len(failed)))


def getDataFrame(tsv, ksminor_filter=None, ksminor_id=None, rename=None, transpose=False):
  """
  Tsv to pandas dataframe, and filters if specified.
  """
  # filter
  df = pd.read_table(tsv)

  if ksminor_filter:
    if ksminor_id is None:
      raise ValueError("Provide Keyspace ID for filtering.")

    df = df[df[str(ksminor_id)].str.contains(ksminor_filter)==False]

  # explore set with copy warning
  if rename:
    df = df.rename(columns=rename)

  if transpose:
    df.set_index(rename[ksminor_id], inplace=True)
    return df.transpose()

  return df


if __name__ == '__main__':

  parser = argparse.ArgumentParser(description = "Populate FrameSpace Reference Server")

  parser.add_argument("-c", "--config", required=False, type=str, 
                      help="Input config.")

  parser.add_argument("-H", "--host", required=False, type=str, 
                      help="Mongo host.")

  parser.add_argument("-p", "--port", required=False, type=int, help="Mongo port.")

  parser.add_argument("-i", "--inputs", nargs='+', type=str, required=False, default=[None], 
                    help="List of tsvs to input as DataFrames")

  parser.add_argument("-j", "--json", action="store_true", help="If set, input is a list of json vectors (GDC).")


  args = parser.parse_args()

  importer = Importer(args.config, args.inputs, host=args.host, port=args.port, is_json=args.json)

  print importer.config.db_name
  
