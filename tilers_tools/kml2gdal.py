#!/usr/bin/env python
# -*- coding: utf-8 -*-

# 2011-06-14 14:27:08  

###############################################################################
# Copyright (c) 2010, Vadim Shlyakhov
#
#  Permission is hereby granted, free of charge, to any person obtaining a
#  copy of this software and associated documentation files (the "Software"),
#  to deal in the Software without restriction, including without limitation
#  the rights to use, copy, modify, merge, publish, distribute, sublicense,
#  and/or sell copies of the Software, and to permit persons to whom the
#  Software is furnished to do so, subject to the following conditions:
#
#  The above copyright notice and this permission notice shall be included
#  in all copies or substantial portions of the Software.
#
#  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
#  OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
#  THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
#  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
#  FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
#  DEALINGS IN THE SOFTWARE.
#******************************************************************************

import os
import sys
import logging
import re
from optparse import OptionParser
import math

from tiler_functions import *

def kml_parm(hdr,name,lst=False):
    l=re.split('</?%s>' % name,hdr)
    # return only even elements as they are inside <name> </name> 
    return [i.strip() for i in l[1::2]] if lst else l[1].strip()

def find_image(img_path, map_dir):
    imp_path_slashed=img_path.replace('\\','/') # get rid of windows separators
    imp_path_lst=imp_path_slashed.split('/')
    img_patt=imp_path_lst[-1].lower()
    match=[i for i in os.listdir(map_dir if map_dir else '.') if i.lower() == img_patt]
    try:
        return os.path.join(map_dir, match[0])
    except IndexError: raise Exception("*** Image file not found: %s" % img_path)

def overlay2vrt(ol,map_dir,kml_path):
    ld(ol)
    name=kml_parm(ol,'name')
    img_file=kml_parm(ol,'href')
    ld(img_file)
    img_path=find_image(img_file,map_dir)
    base=os.path.splitext(img_path)[0]
    out_format='VRT'
    if options.long_name:
        dst_file= '%s - %s.vrt' % (base,name) # output VRT file
    else:
        dst_file= name + '.vrt'# output VRT file

    pf('%s -> %s' % (img_path,dst_file))
    
    if os.path.exists(dst_file): 
        os.remove(dst_file)

    # http://trac.osgeo.org/proj/wiki/FAQ#ChangingEllipsoidWhycantIconvertfromWGS84toGoogleEarthVirtualGlobeMercator
    out_srs="+proj=merc +a=6378137 +b=6378137 +lat_ts=0.0 +lon_0=0.0 +x_0=0.0 +y_0=0 +k=1.0 +units=m +nadgrids=@null +wktext +no_defs"

    src_ds = gdal.Open(img_path,GA_ReadOnly)    
    dst_drv = gdal.GetDriverByName(out_format)
    dst_ds = dst_drv.CreateCopy(dst_file,src_ds,0)
    del src_ds
    dst_ds.SetProjection(out_srs)    
    
    if '<gx:LatLonQuad>' in ol:
        src_refs=[map(float,i.split(',')) for i in kml_parm(ol,'coordinates').split()]
    else: # assume LatLonBox
        assert '<LatLonBox>' in ol
        north,south,east,west=[float(kml_parm(ol,parm)) for parm in ('north','south','east','west')]
        src_refs=[(west,south),(east,south),(east,north),(west,north)]

    dst_refs=MyTransformer(SRC_SRS=proj_cs2geog_cs(out_srs),DST_SRS=out_srs).transform(src_refs)
    if '<rotation>' in ol:
        north,south,east,west=[float(dst_refs[i][j]) for i,j in ((2,1),(0,1),(1,0),(0,0))]
        angle=math.radians(float(kml_parm(ol,'rotation')))
        dx=east-west
        dy=north-south
        xc=(west +east )/2
        yc=(south+north)/2
        x1=dy*math.sin(angle)
        x2=dx*math.cos(angle)
        y1=dy*math.cos(angle)
        y2=dx*math.sin(angle)
        x0=xc-(x1+x2)/2
        y0=yc-(y1+y2)/2
        ld('west,east',west,east)
        ld('south,north',south,north)
        ld('dx dy',dx,dy)
        ld('xc x0 x1 x2',xc,x0,x1,x2)
        ld('yc y0 y1 y2',yc,y0,y1,y2)
        dst_refs=[(x0+x1,y0),(x0+x1+x2,y0+y2),(x0+x2,y0+y1+y2),(x0,y0+y1)]
    ld(dst_refs)

    w, h=dst_ds.RasterXSize,dst_ds.RasterYSize
    ld('w, h',w, h)
    corners=[(0,h),(w,h),(w,0),(0,0)]
    ids=[str(i+1) for i in range(4)]
    gcps=[gdal.GCP(c[0],c[1],0,p[0],p[1],'',i) for i,p,c in zip(ids,corners,dst_refs)]

    dst_ds.SetGCPs(gcps,out_srs)
    #dst_ds.SetGeoTransform(gdal.GCPsToGeoTransform(gcps))
    dst_ds.SetGeoTransform((0,1,0,0,0,1))
    
    cutline=shape2cutline(kml_path,dst_ds,name)
    if cutline:
        dst_ds.SetMetadataItem('CUTLINE',cutline)
    if name:
        dst_ds.SetMetadataItem('DESCRIPTION',name)

    del dst_ds

def kml2vrt(map_path):
    map_dir, map_fname=os.path.split(map_path)
    f=open(map_path, 'r').read()
    if '<GroundOverlay>' not in f: 
        raise Exception("*** Incorrect file: <GroundOverlay> required")
    overlay_lst=kml_parm(f,'GroundOverlay', lst=True) # get list of <GroundOverlay> content
    for ol in overlay_lst:
        overlay2vrt(ol,map_dir,map_path)

if __name__=='__main__':
    parser = OptionParser(
        usage="usage: %prog [--cut] [--dest-dir=DEST_DIR] MAP_file...",
        version=version,
        description="simple KML converter into GDAL .VRT format")
    parser.add_option("-d", "--debug", action="store_true", dest="debug")
    parser.add_option("-t", "--dest-dir", dest="dest_dir", default='',
        help='destination directory (default: current)')
    parser.add_option("-l", "--long-name", action="store_true", 
        help='give an output file a long name')

    options, args = parser.parse_args()
    if not args:
        parser.error('No input file(s) specified')
    logging.basicConfig(level=logging.DEBUG if options.debug else logging.INFO)

    for f in args:
        kml2vrt(f)
