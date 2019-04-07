# **************************************************************************
# *
# * Authors: Peter Horvath [1]
# *          Pablo Conesa [1]
# *
# * [1] I2PC center
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
import os

from pyworkflow.em import ImageHandler
from pyworkflow.em.convert import Ccp4Header
from pyworkflow.utils import replaceExt, join, getExt, path

from sphire import Plugin


def coordinateToRow(coord, boxSize, boxFile, flipOnY=False, height=None):
    """ Add a scipion coordinate to a box file  """

    # (width, height, foo) = self.inputMicrographs.get().getDim() #get height for flipping on y
    boxLine = coordinateToBox(coord, boxSize, flipOnY=flipOnY, height=height)
    boxFile.write("%s\t%s\t%s\t%s\n" % boxLine)


def coordinateToBox(coord, boxSize, flipOnY=False, height=None):
    """ Plain conversion of Scipion coordinate to the 4 tuple values
    for the box line"""

    # Sphire 0,0 is at bottom-left. But also image are flip vertically
    # Xmipp coordinates origin is defined in the middle. This correction should
    # Also, coordinate x and y refers to bottom, left of the box
    halfBox = int(boxSize/2)
    xCoord = coord.getX() - halfBox
    yCoord = coord.getY() - halfBox

    # Under some circumstances in ".mrc" (xmipp setting ISPG value to 1),
    # cryolo does not flip the image, so we need to flip the coordinate.
    # This flips the image.
    if flipOnY:
        if height is None:
            raise ValueError("height param is mandatory when flipOnY is True")

        yCoord = height - (coord.getY() + halfBox)

    return xCoord, yCoord, boxSize, boxSize


def writeSetOfCoordinates(boxDir, coordSet, micsDir):
    """ Convert a SetOfCoordinates to Cryolo box files.
    Params:
        boxDir: the output directory where to generate the files.
        coordSet: the input SetOfCoordinates that will be converted.
    """
    openedBoxFileName = None
    boxfh = None

    # Get the SOM (SetOfMicrographs)
    micList = coordSet.getMicrographs()

    # Get first mic from mics
    mic = micList.getFirstItem()

    # Get fileName from mic
    fileName = mic.getFileName()

    fliponY, y = getFlippingParams(fileName)

    # Loop through coordinates and generate box files
    for item in coordSet:
        # Define file name (box)
        micName = item.getMicName()
        boxFileName = join(boxDir, replaceExt(micName, "box"))

        # If opened box file is not the same
        if boxFileName != openedBoxFileName:
            #close the previous file handler
            if openedBoxFileName is not None:
                boxfh.close()
            boxfh = open(boxFileName, 'a+')

            # convert micrograph if needed
            mic = micList[item.getMicId()]
            createMic(mic, micsDir)

        # Write the coordinate
        coordinateToRow(item, coordSet.getBoxSize(), boxfh, flipOnY=fliponY, height=y)

    if openedBoxFileName is not None:
        boxfh.close()


def needToFlipOnY(filename):
    """ Returns true if need to flip coordinates on Y"""

    # Get the extension.
    ext = getExt(filename)
    accepted_ext = [".tif", ".tiff", ".jpg"]
    if ext in ".mrc":

        header = Ccp4Header(filename, readHeader=True)

        # 1, cryolo will not flip the image
        ispg = header.getISPG()

        return ispg != 0

    elif ext in accepted_ext:
        return True           # These micrograph coordinates are need to be flipped

    else:
        return False


def getFlippingParams(filename):
    """ Returns params that are needed for flipping """

    flipOnY = needToFlipOnY(filename)
    x, y, z, n = ImageHandler().getDimensions(filename)
    return flipOnY, y


def createMic(mic, micDir):
    """ Return a valid micrograph for CRYOLO:
     If compatible, it will be a link in  micDir
     otherwise it will be a converted micrograph to mrc."""

    path.makePath(micDir)

    # we only copy the micrographs once
    fileName = mic.getFileName()
    extensionFn = getExt(fileName)
    accepted_fformats = [".mrc", ".tif", ".jpg"]
    if extensionFn not in accepted_fformats:
        fileName1 = replaceExt(fileName, "mrc")
        basename = os.path.basename(fileName1)
        dest = os.path.abspath(os.path.join(micDir, basename))
        ih = ImageHandler()  # instantiate as an object
        ih.convert(fileName, dest)

    else:
        # No conversion is needed
        basename = os.path.basename(fileName)
        source = os.path.abspath(fileName)
        dest = os.path.abspath(join(micDir, basename))
        path.createLink(source, dest)

    return dest


# --------------------------- UTILS functions -------------------------------
def preparingCondaProgram(prot, program, params='', label=''):
    with open(prot._getExtraPath('script_%s.sh' % label), "w") as f:
        lines = '%s\n' % Plugin.getCryoloEnvActivation()
        lines += 'export CUDA_VISIBLE_DEVICES=%s\n' % (' '.join(str(g) for g in prot.getGpuList()))
        lines += '%s %s\n' % (program, params)
        f.write(lines)


def getBoxSize(prot):
    # if self.bxSzFromCoor:
    #     return self.coordsToBxSz.get().getBoxSize()
    # else:
    return prot.boxSize.get()