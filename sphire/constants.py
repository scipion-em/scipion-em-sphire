# **************************************************************************
# *
# * Authors:    Peter Horvath (phorvath@cnb.csic.es) [1]
# *             Pablo Conesa (pconesa@cnb.csic.es) [1]
# *             J.M. De la Rosa Trevin (delarosatrevin@scilifelab.se) [2]
# *             Jorge Jiménez jimenez@cnb.csic.es) [1]
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


def getCryoloEnvName(version, useCpu=False):
    return f"cryolo{'CPU' if useCpu else ''}-{version}"


def getNaparyEnvName(version):
    return f"napari_cryolo-{version}"


V1_8_2 = "1.8.2"
V1_8_4 = "1.8.4"
V1_8_5 = "1.8.5"
V1_9_3 = "1.9.3"

VERSIONS = [V1_8_2, V1_8_4, V1_8_5, V1_9_3]
CRYOLO_DEFAULT_VER_NUM = VERSIONS[-1]

DEFAULT_ENV_NAME = getCryoloEnvName(CRYOLO_DEFAULT_VER_NUM)
DEFAULT_ACTIVATION_CMD = 'conda activate ' + DEFAULT_ENV_NAME
CRYOLO_ENV_ACTIVATION = 'CRYOLO_ENV_ACTIVATION'

DEFAULT_ENV_NAME_CPU = getCryoloEnvName(CRYOLO_DEFAULT_VER_NUM, useCpu=True)
DEFAULT_ACTIVATION_CMD_CPU = 'conda activate ' + DEFAULT_ENV_NAME_CPU
CRYOLO_ENV_ACTIVATION_CPU = 'CRYOLO_ENV_ACTIVATION_CPU'

CRYOLO_CUDA_LIB = 'CRYOLO_CUDA_LIB'


# Model constants
def _modelFn(modelKey):
    return f'gmodel_phosnet_{modelKey}.h5'


CRYOLO_GENMOD_VAR = 'CRYOLO_GENERIC_MODEL'
CRYOLO_GENMOD_NN_VAR = 'CRYOLO_GENERIC_DENOISED_MODEL'
CRYOLO_GENMOD = 'cryolo_model'

CRYOLO_GENMOD_202005 = '202005_N63_c17'
CRYOLO_GENMOD_202005_FN = _modelFn(CRYOLO_GENMOD_202005)

CRYOLO_GENMOD_NN_202005 = '202005_nn_N63_c17'
CRYOLO_GENMOD_NN_202005_FN = _modelFn(CRYOLO_GENMOD_NN_202005)

# Default model (latest usually)
CRYOLO_GENMOD_DEFAULT = os.path.join(f"{CRYOLO_GENMOD}-{CRYOLO_GENMOD_202005}",
                                     CRYOLO_GENMOD_202005_FN)
CRYOLO_GENMOD_NN_DEFAULT = os.path.join(f"{CRYOLO_GENMOD}-{CRYOLO_GENMOD_NN_202005}",
                                        CRYOLO_GENMOD_NN_202005_FN)

# crYOLO supported input formats for micrographs
CRYOLO_SUPPORTED_FORMATS = [".mrc", ".tif", ".tiff", ".jpg"]

# Input options for the training model
INPUT_MODEL_GENERAL = 0
INPUT_MODEL_GENERAL_DENOISED = 1
INPUT_MODEL_OTHER = 2
INPUT_MODEL_GENERAL_NS = 3

CRYOLO_NS_GENMOD_VAR = 'CRYOLO_NS_GENERIC_MODEL'
CRYOLO_NS_GENMOD = 'cryolo_negstain_model'
CRYOLO_NS_GENMOD_20190226 = '20190226'
CRYOLO_NS_GENMOD_20190226_FN = f"gmodel_phosnet_negstain_{CRYOLO_NS_GENMOD_20190226}.h5"
CRYOLO_NS_GENMOD_DEFAULT = os.path.join(f"{CRYOLO_NS_GENMOD}-{CRYOLO_NS_GENMOD_20190226}",
                                        CRYOLO_NS_GENMOD_20190226_FN)

JANNI_GENMOD_VAR = 'JANNI_GENERIC_MODEL'
JANNI_GENMOD = "janni_model"
JANNI_GENMOD_20190703 = "20190703"
JANNI_GENMOD_20190703_FN = f"gmodel_janni_{JANNI_GENMOD_20190703}.h5"
JANNI_GENMOD_DEFAULT = os.path.join(f"{JANNI_GENMOD}-{JANNI_GENMOD_20190703}",
                                    JANNI_GENMOD_20190703_FN)

# Napari variables
V0_3_11 = '0.3.11'

defaultVersion = V0_3_11

NAPARI_ACTIVATION_CMD = 'conda activate %s' % getNaparyEnvName(defaultVersion)
NAPARI_BOXMANAGER = 'napari_boxmanager'
CBOX_FILAMENTS_FOLDER = 'CBOX_FILAMENTS_TRACED'
NAPARI_VIEWER_CBOX_FILES = 'napariViewerCboxFiles'

# Filament parameters
STRAIGHTNESS_METHOD = ['NONE', 'LINE_STRAIGHTNESS', 'RMSD']
DIRECTIONAL_METHOD = ['CONVOLUTION', 'PREDICTED']
