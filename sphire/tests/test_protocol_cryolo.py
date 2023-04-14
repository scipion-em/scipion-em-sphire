# **************************************************************************
# *
# * Authors:     Pablo Conesa (pconesa@cnb.csic.es) [1]
# *              Peter Horvath (phorvath@cnb.csic.es) [1]
# *
# * [1] I2PC center
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

import pyworkflow.utils as pwutils
from pyworkflow.tests import BaseTest, setupTestProject, DataSet, setupTestOutput
from pyworkflow.plugin import Domain
from pyworkflow.utils import magentaStr
import pwem.objects as emobj
from pwem.protocols.protocol_import import ProtImportMicrographs, ProtImportCoordinates
from pwem.emlib.image import ImageHandler
from pwem.convert import Ccp4Header

import sphire.convert as convert
import sphire.protocols as protocols
from ..constants import (INPUT_MODEL_OTHER, INPUT_MODEL_GENERAL_NS,
                         INPUT_MODEL_GENERAL)


XmippProtPreprocessMicrographs = Domain.importFromPlugin(
    'xmipp3.protocols', 'XmippProtPreprocessMicrographs', doRaise=True)


class TestSphireConvert(BaseTest):
    @classmethod
    def setUpClass(cls):
        cls.ds = DataSet.getDataSet('relion_tutorial')
        setupTestOutput(cls)

    def testConvertCoords(self):
        import time
        time.sleep(10)
        boxSize = 100
        boxDir = self.getOutputPath('boxDir')
        pwutils.makePath(boxDir)
        HEADER = """
data_cryolo

loop_
_CoordinateX #1
_CoordinateY #2
_Width #3
_Height #4
_Confidence #5
"""

        def _convert(coordsIn, yFlipHeight=None):
            tmpFile = os.path.join(boxDir, 'tmp.cbox')
            # Write input coordinates
            writer = convert.CoordBoxWriter(boxSize, yFlipHeight=yFlipHeight)
            writer.open(tmpFile)
            writer._file.write(HEADER)  # required for cbox
            for x, y, _, _, _, _ in coordsIn:
                writer.writeCoord(emobj.Coordinate(x=x, y=y))
            writer.close()

            reader = convert.CoordBoxReader(boxSize, yFlipHeight=yFlipHeight)
            coordsOut = [c for c in reader.iterCoords(tmpFile)]

            return coordsOut

        coordsIn = [(100, 100, 0., 0., 0, 100), (100, 200, 0., 0.,  0, 100),
                    (200, 100, 0., 0.,  0, 100), (200, 200, 0., 0.,  0, 100)]

        # Case 1: No flip
        coordsOut = _convert(coordsIn)
        for c1, c2 in zip(coordsIn, coordsOut):
            self.assertEqual(c1, c2)

        # Case 2: Flipping on Y
        coordsOut = _convert(coordsIn, yFlipHeight=300)
        for c1, c2 in zip(coordsIn, coordsOut):
            self.assertEqual(c1, c2)

    def testConvertMic(self):
        """Check extension of the input micrographs"""
        micDir = self.getOutputPath('micDir')
        os.mkdir(micDir)

        mrcMic = TestSphireConvert.ds.getFile('micrographs/006.mrc')
        spiMic = os.path.join(micDir, "mic.spi")
        ImageHandler().convert(mrcMic, spiMic)

        mic = emobj.Micrograph(objId=1, location=spiMic)
        # Invoke the createMic function
        convert.convertMicrographs([mic], micDir)
        expectedDest = os.path.join(micDir,
                                    convert.getMicFn(mic, "mrc"))
        print(expectedDest)

        # If ext is not in [".mrc", ".tif", ".jpg"] return .mrc
        self.assertTrue(os.path.exists(expectedDest),
                        "spi file wasn't converted to mrc.")

    def testWriteSetOfCoordinatesWithoutFlip(self):
        from collections import OrderedDict
        # Define a temporary sqlite file for micrographs
        fn = self.getOutputPath('convert_mics.sqlite')
        mics = emobj.SetOfMicrographs(filename=fn)
        # Create SetOfCoordinates data
        # Define a temporary sqlite file for coordinates
        fn = self.getOutputPath('convert_coordinates.sqlite')
        coordSet = emobj.SetOfCoordinates(filename=fn)
        coordSet.setBoxSize(60)
        coordSet.setMicrographs(mics)

        data = OrderedDict()
        data['006'] = [(30, 30)]
        data['016'] = [(40, 40)]

        micList = []
        for key, coords in data.items():
            mic = emobj.Micrograph(self.ds.getFile('micrographs/%s.mrc' % key))
            mics.append(mic)
            micList.append(mic)
            print("Adding mic: %s, id: %s" % (key, mic.getObjId()))

            for x, y in coords:
                coord = emobj.Coordinate(x=x, y=y)
                coord.setMicrograph(mic)
                coordSet.append(coord)

        # Get boxDirectory
        boxFolder = self.getOutputPath('boxFolder')
        os.mkdir(boxFolder)

        micFolder = self.getOutputPath('micFolder')
        pwutils.makePath(micFolder)

        # Invoke the write set of coordinates method
        convert.writeSetOfCoordinates(boxFolder, coordSet)
        convert.convertMicrographs(micList, micFolder)

        # Assert output of writesetofcoordinates
        for mic in micList:
            boxFile = os.path.join(boxFolder,
                                   convert.getMicFn(mic, "box"))
            self.assertTrue(os.path.exists(boxFile),
                            'Missing box file: %s' % boxFile)
            micFile = os.path.join(micFolder,
                                   convert.getMicFn(mic, "mrc"))
            self.assertTrue(os.path.exists(micFile),
                            'Missing box file: %s' % micFile)

        # Assert coordinates in box files
        fh = open(os.path.join(boxFolder, '006.box'))
        box1 = fh.readline()
        fh.close()
        box1 = box1.split('\t')
        self.assertEquals(box1[0], '0')
        self.assertEquals(box1[1], '964')

    def testFlipAssessment(self):
        mrcFile = self.ds.getFile('micrographs/006.mrc')

        # test wrong ispg value (0) in mrc file
        self.assertTrue(convert.needToFlipOnY(mrcFile),
                        "needToFlipOnY wrong for bad mrc.")

        # test non mrc file
        self.assertFalse(convert.needToFlipOnY('dummy.foo'),
                         "needToFlipOnY wrong for non mrc.")

        # Test right ispg value (0 in mrc file)
        # Copy 006
        goodMrc = self.getOutputPath('good_ispg.mrc')
        pwutils.copyFile(mrcFile, goodMrc)

        # Change the ISPG value in the file header
        header = Ccp4Header(goodMrc, readHeader=True)
        header.setISPG(0)
        header.writeHeader()

        # test good mrc file
        self.assertFalse(convert.needToFlipOnY(goodMrc),
                         "needToFlipOnY wrong for good mrc.")

    def testGetFlippingParams(self):
        mrcFile = self.ds.getFile('micrographs/006.mrc')
        y = convert.getFlipYHeight(mrcFile)

        # test if image dimension is right
        self.assertEquals(y, 1024, "Y dimension of the micrograph is not correct.")

    def testInputSizeRounding(self):
        msg = "Input size rounding to the lower is wrong."
        rounded = convert.roundInputSize(1000)
        self.assertEqual(rounded, 992, msg)

        rounded = convert.roundInputSize(60)
        self.assertEqual(rounded, 64, msg)

        rounded = convert.roundInputSize(320)
        self.assertEqual(rounded, 320, msg)


class TestCryolo(BaseTest):
    @classmethod
    def setUpClass(cls):
        setupTestProject(cls)
        cls.ds = DataSet.getDataSet('relion_tutorial')
        cls.runImportMicrograph()
        cls.runMicPreprocessing()
        cls.runImportCoords()

    @classmethod
    def runImportMicrograph(cls):
        """ Run an Import micrographs protocol. """
        cls.protImport = cls.newProtocol(
            ProtImportMicrographs,
            samplingRateMode=0,
            filesPath=cls.ds.getFile('micrographs/*.mrc'),
            samplingRate=3.54,
            magnification=59000,
            voltage=300,
            sphericalAberration=2)

        print(magentaStr(f"\n==> Importing data - micrographs:"))
        cls.launchProtocol(cls.protImport)

    @classmethod
    def runMicPreprocessing(cls):
        cls.protPreprocess = cls.newProtocol(
            XmippProtPreprocessMicrographs,
            inputMicrographs=cls.protImport.outputMicrographs,
            objLabel="crop 50px",
            doCrop=True, cropPixels=25)

        print(magentaStr(f"\n==> Preprocessing micrographs:"))
        cls.launchProtocol(cls.protPreprocess)

    @classmethod
    def runImportCoords(cls):
        """ Run an Import coords protocol. """
        cls.protImportCoords = cls.newProtocol(
            ProtImportCoordinates,
            importFrom=ProtImportCoordinates.IMPORT_FROM_EMAN,
            objLabel='import EMAN coordinates',
            filesPath=cls.ds.getFile('pickingEman/info/'),
            inputMicrographs=cls.protPreprocess.outputMicrographs,
            filesPattern='*.json',
            boxSize=65)

        print(magentaStr(f"\n==> Importing data - coordinates:"))
        cls.launchProtocol(cls.protImportCoords)

    def _runPickingTest(self, boxSize, objLabel, boxSizeFactor=1.0):
        protcryolo = self.newProtocol(
            protocols.SphireProtCRYOLOPicking,
            objLabel=objLabel,
            inputMicrographs=self.protPreprocess.outputMicrographs,
            boxSize=boxSize,
            input_size=750,
            boxSizeFactor=boxSizeFactor,
            streamingBatchSize=10)

        print(magentaStr(f"\n==> Testing sphire - cryolo picking:"))
        self.launchProtocol(protcryolo)
        self.assertSetSize(protcryolo.outputCoordinates,
                           msg="There was a problem picking with crYOLO")
        return protcryolo

    def testPickingNoBoxSize(self):
        # No box size provided by user
        prot = self._runPickingTest(boxSize=0,
                                    objLabel='Picking - Box size estimated',
                                    boxSizeFactor=1.5)
        self.assertEqual(prot.outputCoordinates.getBoxSize(), 72,
                         "Estimated box size does not match.")

    def testPickingBoxSize(self):
        # No training mode picking, box size provided by user
        self._runPickingTest(boxSize=50, objLabel='Picking - Box size provided')

    def testPickingValidationGeneral(self):
        # No training mode picking
        protcryolo = self.newProtocol(
            protocols.SphireProtCRYOLOPicking,
            inputMicrographs=self.protPreprocess.outputMicrographs,
            input_size=750,
            streamingBatchSize=10)

        # Get model
        model_file_original = protcryolo.getInputModel()
        model_file_test = pwutils.replaceExt(model_file_original, "h5_test")
        os.rename(model_file_original, model_file_test)

        self.assertTrue(protcryolo._validate())
        os.rename(model_file_test, model_file_original)

    def _runTraining(self, fineTune=False):
        # crYOLO training
        fineTuneStr = "(fine-tune)" if fineTune else ""
        protTraining = self.newProtocol(
            protocols.SphireProtCRYOLOTraining,
            objLabel=f"Training {fineTuneStr}",
            inputMicrographs=self.protPreprocess.outputMicrographs,
            inputCoordinates=self.protImportCoords.outputCoordinates,
            boxSize=65,
            input_size=750,
            eFlagParam=2,
            doFineTune=fineTune,
            batchSize=2,
            nb_epochVal=2)

        print(magentaStr(f"\n==> Testing sphire - cryolo training {fineTuneStr}:"))
        self.launchProtocol(protTraining)
        self.assertIsNotNone(protTraining.outputModel)

        # Picking with a trained model
        protPicking = self.newProtocol(
            protocols.SphireProtCRYOLOPicking,
            objLabel="Picking after training",
            inputMicrographs=self.protPreprocess.outputMicrographs,
            inputModelFrom=INPUT_MODEL_OTHER,
            inputModel=protTraining.outputModel,
            boxSize=50,
            input_size=750,
            streamingBatchSize=10)

        print(magentaStr(f"\n==> Testing sphire - cryolo picking (after training):"))
        self.launchProtocol(protPicking)
        self.assertSetSize(protPicking.outputCoordinates,
                           size=5916, diffDelta=0.3,
                           msg="There was a problem picking with crYOLO")

    def testTraining(self):
        self._runTraining(fineTune=False)

    def testTraningFineTune(self):
        self._runTraining(fineTune=True)


class TestCryoloNegStain(BaseTest):
    """ Test cryolo protocol for negative stain images"""
    @classmethod
    def setUpClass(cls):
        setupTestProject(cls)
        cls.ds = DataSet.getDataSet('negative_stain')
        cls.runImportMicrograph()

    @classmethod
    def runImportMicrograph(cls):
        """ Run an Import micrograph protocol. """
        cls.protImport = cls.newProtocol(
            ProtImportMicrographs,
            filesPath=cls.ds.getFile('allMics'),
            samplingRate=3.54,
            magnification=59000,
            voltage=300,
            sphericalAberration=2)

        print(magentaStr(f"\n==> Importing data - micrographs:"))
        cls.launchProtocol(cls.protImport)

    def testPickingNS(self):
        protPickingNS = self.newProtocol(protocols.SphireProtCRYOLOPicking,
                                         objLabel="Picking on neg. stain mics",
                                         inputMicrographs=self.protImport.outputMicrographs,
                                         inputModelFrom=INPUT_MODEL_GENERAL_NS,
                                         lowPassFilter=False,
                                         conservPickVar=0.2)

        print(magentaStr(f"\n==> Testing sphire - cryolo picking:"))
        self.launchProtocol(protPickingNS)
        self.assertSetSize(protPickingNS.outputCoordinates,
                           msg="There was a problem picking with crYOLO")


class TestCryoloTomo(BaseTest):
    """ Test cryolo protocol for tomograms picking"""

    @classmethod
    def setUpClass(cls):
        setupTestProject(cls)
        cls.dataset = DataSet.getDataSet('tomo-em')
        cls.tomogram = cls.dataset.getFile('*.em')

    @classmethod
    def _runImportTomograms(cls):
        with pwutils.weakImport('tomo'):
            import tomo.protocols
        protImport = cls.newProtocol(
            tomo.protocols.ProtImportTomograms,
            filesPath=cls.tomogram,
            filesPattern='',
            acquisitionAngleMax=40,
            acquisitionAngleMin=-40,
            samplingRate=1.35)

        print(magentaStr(f"\n==> Importing data - tomograms:"))
        cls.launchProtocol(protImport)
        return protImport

    def test_pickingTomograms(self):
        protImport = self._runImportTomograms()
        self.assertIsNotNone(protImport.Tomograms,
                             "There was a problem with Import Tomograms protocol")

        sphireProtCRYOLOTomoPicking = self.newProtocol(protocols.SphireProtCRYOLOTomoPicking,
                                                       inputTomograms=protImport.Tomograms,
                                                       inputModelFrom=INPUT_MODEL_GENERAL,
                                                       lowPassFilter=False)

        print(magentaStr(f"\n==> Testing sphire - cryolo tomo picking:"))
        self.launchProtocol(sphireProtCRYOLOTomoPicking)
        self.assertIsNotNone(sphireProtCRYOLOTomoPicking.output3DCoordinates,
                             "There was a problem with tomo picking protocol")
        self.assertTrue(sphireProtCRYOLOTomoPicking.output3DCoordinates.getSize() > 0,
                        "There was a problem with tomo picking protocol")
        return sphireProtCRYOLOTomoPicking
