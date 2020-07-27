from gbdxtools import CatalogImage, Interface
import os, sys
import numpy as np
import geopandas as gpd
from matplotlib import pyplot as plt
from scipy.misc import bytescale
import shapely
from shapely.wkt import loads
import pandas as pd
from shapely.geometry import box
from fiona.crs import from_epsg
import shutil
import requests
import rasterio as rio

## Provide a sample query for import
sample_query = 'item_type:WV03_VNIR OR item_type:WV02 OR item_type:WV04 OR item_type:ESAProduct'

gbdx = Interface()

def get_preview_image_arr(catid):
    '''
    gbdx: interface object for GBDX access
    catid: catolog ID for image asset
    
    returns: numpy array for preview image
    '''

    my_url = gbdx.catalog.get(catid)['properties']['browseURL']
    response = requests.get(my_url, stream=True)
    temp = 'temp.png'
    with open(temp, 'wb') as file:
        shutil.copyfileobj(response.raw, file)
    del response
    
    with rio.open(temp) as src:
        arr = src.read()
        
    os.remove(temp)
    
    return arr

def flatten_dict(d):
    def expand(key, value):
        if isinstance(value, dict):
            return [ (key + '.' + k, v) for k, v in flatten_dict(value).items() ]
        else:
            return [ (key, value) ]

    items = [ item for k, v in d.items() for item in expand(k, v) ]

    return dict(items)

def flatten_dict_dg(d):
    def expand(key, value):
        if isinstance(value, dict):
            return [ (key + '.' + k, v) for k, v in flatten_dict(value).items() ]
        else:
            return [ (key, value) ]

    items = [ item for k, v in d.items() for item in expand(k, v) ]
    d = dict(items)
    d['properties.item_type'] = d['properties.item_type'][-1]
    
    return d

## construct some queries
# query = 'item_type:QB OR item_type:GE01'
# query = 'item_type:GE01'
# query = 'item_type:QB02'
# query = 'item_type:ESAProduct'






def query_gbdx_by_geometry(geom, query, count=5000, min_year=2000, max_year=2020, out_epsg=None):

    pt_dfs = []
    gbdx = Interface()

    # Unary union ensures single geometry, and AOI needs to be in WKT form
    try:
        aoi = geom.unary_union.wkt
    except:
        aoi = geom.wkt
        
    recs = gbdx.vectors.query(aoi, query, count=count) # count keyword default is 100, # results returned
    
    # Convert to a dataframe!
    results = pd.DataFrame([flatten_dict_dg(r) for r in recs])
        
    # Convert month-day-year to integer fields
    yr = [int(d.split('-')[0]) for d in results['properties.item_date']]
    mo = [int(d.split('-')[1]) for d in results['properties.item_date']]
    day = [int(d.split('-')[2].split('T')[0]) for d in results['properties.item_date']]
    results['month'] = mo
    results['year'] = yr
    results['day'] = day
        
    results = results.query('year > {}'.format(min_year))
    results = results.query('year < {}'.format(max_year))
    
    # Add the geometry columns
    # add geometries as a column for wv3
    poly_list = []
    for coordinates in results['geometry.coordinates']:
        
        points= [shapely.geometry.Point(p[0], p[1]) for p in coordinates[0][0]]
        coords = sum(map(list, (p.coords for p in points)), [])
        poly = shapely.geometry.Polygon(coords)
        poly_list.append(poly)

    results['geometry'] = poly_list
    results = gpd.GeoDataFrame(results)
    results.crs = from_epsg(4326)
    
    # there are many duplicate rows for a given ID. possible group by them and return the first result??
    
    if out_epsg is not None:
        results.to_crs(epsg=out_epsg)
        
    return results

# there are many duplicate rows for a given ID. possible group by them and return the first result??
def reduce_gbdx_results(gbdx_df, prop='properties.attributes.catalogID'):
    
    ## let's try reducing by grouping ids
    res_group = gbdx_df.groupby(prop)
    
    res_l = []
    for group in res_group:
        
        if group[1].shape[0] > 1:
            new_df = group[1].iloc[[0]]
            res_l.append(new_df)
        else:
            res_l.append(group[1])
            
    res = pd.concat(res_l)
    res = gpd.GeoDataFrame(res)
    res.crs = gbdx_df.crs
    
    return res

    
