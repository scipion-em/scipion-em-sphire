# **************************************************************************
# *
# *  Authors:     Szu-Chi Chung (phonchi@stat.sinica.edu.tw) 
# *
# * SABID Laboratory, Institute of Statistical Science, Academia Sinica
# *
# * This program is free software; you can redistribute it and/or modify
# * it under the terms of the GNU General Public License as published by
# * the Free Software Foundation; either version 2 of the License, or
# * (at your option) any later version.
# *
# * This program is distributed in the hope that it will be useful,
# * but WITHOUT ANY WARRANTY; without even the implied warranty of
# * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# * GNU General Public License for more details.
# *
# * You should have received a copy of the GNU General Public License
# * along with this program; if not, write to the Free Software
# * Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA
# * 02111-1307  USA
# *
# *  All comments concerning this program package may be sent to the
# *  e-mail address 'scipion@cnb.csic.es'
# *
# **************************************************************************
from sparx import *
from sys import argv
import numpy as np


def saveclass(refimgs, particle_imgs, not_processed, all_params, initial_params, out_dir):
    ref = EMData.read_images(refimgs)
    images = EMData.read_images(particle_imgs)
    ids = []
    with open(not_processed, 'r') as infile:
        for line in infile:
            ids.append(line.split()[0])
    
    classes =[]
    for i in xrange(EMUtil.get_image_count(refimgs)):
        imagesc = get_im(refimgs,i)
        classes.append(imagesc.get_attr('members'))
    
    np.save(out_dir+"/classes.npy", classes)
    
    ave = model_blank(images[0].get_xsize(),images[0].get_xsize())
    for i in xrange(len(ids)):   
        Util.add_img(ave, images[i])
        Util.mul_scalar(ave, 1.0 /float(len(ids)) )
    
    ave1  = resample(ave, float(ref[0].get_xsize())/images[0].get_xsize())
    for i, img in enumerate(ref):
        img.write_image(out_dir+"/output.hdf",i)
    ave1.write_image(out_dir+"/output.hdf",i+1)
    
    params = read_text_row(all_params)
    params2 = read_text_row(initial_params)
    
    P = []
    ratios = float(ref[0].get_xsize())/images[0].get_xsize()
    for i in xrange(len(params)):
        pi = combine_params2( params2[i][0], params2[i][1], params2[i][2], params2[i][3], \
               params[i][0], params[i][1]/ratios, params[i][2]/ratios, params[i][3])
        P.append(pi)
    
    np.save(out_dir+"/params.npy", P)
    print("OK")

if __name__ == '__main__':
    if len(sys.argv) == 7:
        refimgs = sys.argv[1]
        particle_imgs = sys.argv[2]
        not_processed = sys.argv[3]
        all_params = sys.argv[4]
        initial_params = sys.argv[5]
        out_dir = sys.argv[6]
        saveclass(refimgs, particle_imgs, not_processed, all_params, initial_params, out_dir)
    else:
        print("usage: %s outputFile" % os.path.basename(sys.argv[0]))