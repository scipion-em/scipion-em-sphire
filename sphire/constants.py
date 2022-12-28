# -*- coding: utf-8 -*
# **************************************************************************
# *
# * Authors:    Peter Horvath [1]
# *             Pablo Conesa  [1]
# *             J.M. De la Rosa Trevin (delarosatrevin@scilifelab.se) [2]
# *             Jorge Jiménez [1]
# *
# *
# * [1] Unidad de  Bioinformatica of Centro Nacional de Biotecnologia , CSIC
# * [2] SciLifeLab, Stockholm University
# *
# * This program is free software; you can redistribute it and/or modify
# * it under the terms of the GNU General Public License as published by
# * the Free Software Foundation; either version 3 of the License, or
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

import os


# crYOLO ###############################################################################################################

def getCryoloEnvName(version, useCpu=False):
    return "cryolo%s-%s" % ('CPU' if useCpu else '', version)


V_UNKNOWN = 'v0.0.0'
V1_5_4 = "1.5.4"
V1_6_1 = "1.6.1"
V1_7_2 = "1.7.2"
V1_7_6 = "1.7.6"
V1_8_0 = "1.8.0"
V1_8_2 = "1.8.2"
V1_8_4 = "1.8.4"

VERSIONS = [V1_5_4, V1_6_1, V1_7_2, V1_7_6, V1_8_2, V1_8_4]
CRYOLO_DEFAULT_VER_NUM = V1_8_4

DEFAULT_ENV_NAME = getCryoloEnvName(CRYOLO_DEFAULT_VER_NUM)
DEFAULT_ACTIVATION_CMD = 'conda activate ' + DEFAULT_ENV_NAME
CRYOLO_ENV_ACTIVATION = 'CRYOLO_ENV_ACTIVATION'

DEFAULT_ENV_NAME_CPU = getCryoloEnvName(CRYOLO_DEFAULT_VER_NUM, useCpu=True)
DEFAULT_ACTIVATION_CMD_CPU = 'conda activate ' + DEFAULT_ENV_NAME_CPU
CRYOLO_ENV_ACTIVATION_CPU = 'CRYOLO_ENV_ACTIVATION_CPU'

CRYOLO_CUDA_LIB = 'CRYOLO_CUDA_LIB'


# Model constants
def _modelFn(modelKey):
    return 'gmodel_phosnet_%s.h5' % modelKey


CRYOLO_GENMOD_VAR = 'CRYOLO_GENERIC_MODEL'
CRYOLO_GENMOD_NN_VAR = 'CRYOLO_GENERIC_DENOISED_MODEL'
CRYOLO_GENMOD = 'cryolo_model'

CRYOLO_GENMOD_201909 = '201909'
CRYOLO_GENMOD_201909_FN = _modelFn(CRYOLO_GENMOD_201909)

CRYOLO_GENMOD_201910 = '201910'
CRYOLO_GENMOD_201910_FN = _modelFn(CRYOLO_GENMOD_201910)

CRYOLO_GENMOD_202002 = '202002_N63'
CRYOLO_GENMOD_202002_FN = _modelFn(CRYOLO_GENMOD_202002)

CRYOLO_GENMOD_202005 = '202005_N63_c17'
CRYOLO_GENMOD_202005_FN = _modelFn(CRYOLO_GENMOD_202005)

CRYOLO_GENMOD_NN_202005 = '202005_nn_N63_c17'
CRYOLO_GENMOD_NN_202005_FN = _modelFn(CRYOLO_GENMOD_NN_202005)

# Default model (latest usually)
CRYOLO_GENMOD_DEFAULT = os.path.join(CRYOLO_GENMOD + "-" + CRYOLO_GENMOD_202005,
                                     CRYOLO_GENMOD_202005_FN)
CRYOLO_GENMOD_NN_DEFAULT = os.path.join(CRYOLO_GENMOD + "-" + CRYOLO_GENMOD_NN_202005,
                                        CRYOLO_GENMOD_NN_202005_FN)

# crYOLO supported input formats for micrographs
CRYOLO_SUPPORTED_FORMATS = [".mrc", ".tif", ".tiff", ".jpg"]

# Input options for the training model
INPUT_MODEL_GENERAL = 0
INPUT_MODEL_GENERAL_DENOISED = 1
INPUT_MODEL_OTHER = 2
INPUT_MODEL_GENERAL_NS = 3


# crYOLO - NEGATIVE STAIN ##############################################################################################

def _negStainModelFn(modelKey):
    return 'gmodel_phosnet_negstain_{}.h5'.format(modelKey)


CRYOLO_NS_GENMOD_VAR = 'CRYOLO_NS_GENERIC_MODEL'
CRYOLO_NS_GENMOD = 'cryolo_negstain_model'
CRYOLO_NS_GENMOD_20190226 = '20190226'
CRYOLO_NS_GENMOD_20190226_FN = _negStainModelFn(CRYOLO_NS_GENMOD_20190226)
CRYOLO_NS_GENMOD_DEFAULT = os.path.join(CRYOLO_NS_GENMOD + "-" + CRYOLO_NS_GENMOD_20190226,
                                        CRYOLO_NS_GENMOD_20190226_FN)


# JANNI ################################################################################################################

def _janniModelFn(modelKey):
    return 'gmodel_janni_{}.h5'.format(modelKey)


JANNI_GENMOD_VAR = 'JANNI_GENERIC_MODEL'
JANNI_GENMOD = "janni_model"  # Name
JANNI_GENMOD_20190703 = "20190703"  # Version
JANNI_GENMOD_20190703_FN = _janniModelFn(JANNI_GENMOD_20190703)  # File name with extension
JANNI_GENMOD_DEFAULT = os.path.join("{}-{}".format(JANNI_GENMOD, JANNI_GENMOD_20190703),
                                    JANNI_GENMOD_20190703_FN)
