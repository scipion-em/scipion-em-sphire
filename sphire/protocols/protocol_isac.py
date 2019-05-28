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


import numpy as np 
import os
import shutil
import pyworkflow.em as em
import pyworkflow.em.metadata as md

from pyworkflow.em.protocol import ProtClassify2D, SetOfClasses2D
from pyworkflow.utils.path import makePath
from pyworkflow.protocol.params import (PointerParam, BooleanParam,
                                        FloatParam, IntParam, Positive, StringParam)
from relion.convert import writeSetOfParticles, rowToAlignment, relionToLocation
import eman2

class ProtISAC(ProtClassify2D):
    """ Wrapper to ISAC program.
    """
    _label = 'perform ISAC'
    
    def __init__(self, **args):
        ProtClassify2D.__init__(self, **args)
        if self.numberOfMpi.get() < 2:
            self.numberOfMpi.set(2)
    
    def _defineFileNames(self):
        """ Centralize how files are called within the protocol. """
        myDict = {
                  'input_particles': self._getPath('input_particles.star'),
                  'input_particles_m': self._getPath('input_particles_m.star'),
                  'input_particles_m2': self._getPath('input_particles_m2.star'),
                  'input_particles_m3': self._getPath('input_particles_m3.star'),
                  'output_hdf': self._getExtraPath('classaverage_2d.hdf'),
                  'class_average': self._getPath() + '/Class2D/class_averages.hdf',
                  'class_average_b': self._getPath() + '/Class_Beau/class_averages.hdf',
                  'processfile': self._getPath() + '/Class2D/processed_images.txt',
                  'notprocessfile': self._getPath() + '/Class2D/not_processed_images.txt',
                  'params': self._getPath()+'/Class2D/all_parameters.txt',
                  'params2': self._getPath()+'/Class2D/2dalignment/initial2Dparams.txt',
                  'out_particles': self._getPath() + '/Particles/sphire_stack.hdf',
                  'out_class': self._getPath() + '/output.hdf',
                  'out_db': "bdb:"+self._getPath() + '/Particles#stack',
                  'isac_dir': self._getPath() + '/Class2D'
                  }
        self._updateFilenamesDict(myDict)
    
    # --------------------------- DEFINE param functions -----------------------
    def _defineParams(self, form):
        form.addSection(label='Input')
        form.addParam('inputParticles', PointerParam,
                      pointerClass='SetOfParticles',
                      label="Input particles", important=True,
                      help='Select the input images from the project.')
        form.addParam('numberOfImages', IntParam, default=100, validators=[Positive],
                      label='Image per Group',
                      help='Number of images to be generated for a group')
        # Radius
        form.addParam('radius', IntParam, default=40, validators=[Positive],
                      label='Particle radius',
                      help='The original radius of particle')
        form.addParam('doResize', BooleanParam, default=False, label='Resize the paticle', important=True, help='If set to True,resize the particle')
        group1 = form.addGroup('Resize', condition='doResize',
                            help='Resize the particle')
        group1.addParam('target_radius', IntParam, default=29, validators=[Positive],
                      label='Resize particle radius',
                      help='Target resize particle radius')
        
        group1.addParam('target_box_size', IntParam, default=76, validators=[Positive],
                       label='Resize box size',
                       help='Target resize box size')
        form.addParam('doCTF', BooleanParam, default=False, important=True,
                       label='Do CTF correction?',
                       help='If set to True, we must provide CTF information')
        form.addParam('doPhase', BooleanParam, default=False, important=True,
                       label='Is the data collected by phase plate??',
                       help='If set to True, we must provide phase information')

        form.addParam('thld_err', StringParam, default="0.7", important=True,
                       label='Threshold ',
                       help='With increased number of particles per class or in case you expect a high degree\
                       of flexibility in your particle, you should set a higher threshold value (forexample 1.7)')
        form.addParam('doBeautify', BooleanParam, default=False, important=True,
                      label='Beautify ',
                      help='adjust to analytic model?')
        form.addParam('restart', IntParam, default=-1,
                       label='Restart iteration',
                       help='Continue from which iteration')
        form.addParam('extraParams', StringParam,
              default='',
              label='Additional arguments',
              help="In this box command-line arguments may be "
                   "This may be useful for testing developmental options "
                   "and/or expert use of the program")
        form.addParallelSection(threads=1, mpi=2)
    
    # --------------------------- INSERT steps functions -----------------------
    def _insertAllSteps(self):
        self._defineFileNames()
        objId = self.inputParticles.get().getObjId()
        self._insertFunctionStep("convertInputStep", objId)
        self._insertFunctionStep('processStep')
        self._insertFunctionStep('createOutputStep')

    # --------------------------- STEPS functions ------------------------------
    def convertInputStep(self, particlesId):
        """ Create the input file in STAR format as expected by Relion.
        If the input particles comes from Relion, just link the file. 
        """
        imgSet = self.inputParticles.get()
        # Create links to binary files and write the relion .star file
        writeSetOfParticles(imgSet, self._getFileName('input_particles'), outputDir=self._getExtraPath(), fillMagnification=True)
        parti = False
        index = 0
        # sxrelion2sphire needs  numbering in the header
        with open(self._getFileName('input_particles'), 'r') as input_file, open(self._getFileName('input_particles_m'), 'w') as output_file:
            i = 1
            for line in input_file:
                if line.startswith(" _rlnCoordinateX"):
                    parti = True
                if line.startswith(" _rln"):
                    output_file.write(line.strip()+" #%d \n"%i)
                    i = i+1
                    index = i
                else:
                    output_file.write(line)
        # sxrelion2sphire needs  _rlnCoordinateX and _rlnCoordinateY
        if parti == False:
             with open(self._getFileName('input_particles_m'), 'r') as input_file, open(self._getFileName('input_particles_m2'), 'w') as output_file:
                 j = 0 #mutex lock
                 i = 0 #start
                 for line in input_file:
                     if line.startswith("_rln"):
                         output_file.write(line)
                         i = 1
                     elif i == 0:
                         output_file.write(line)
                     elif j == 0:
                         # Create dummy coordinate for extratcion only
                         output_file.write('_rlnCoordinateX #%d\n'%index)
                         output_file.write('_rlnCoordinateY #%d\n'%(index+1))
                         line = line.rstrip()
                         if len(line.split('@')) == 1:
                             lines = line.split('Runs')
                             line = lines[0]+'1@Runs'+lines[1]
                         output_file.write(line+' 0.5 0.5\n')
                         j = 1
                     else:
                         line = line.rstrip()
                         if len(line.split('@')) == 1:
                             lines = line.split('Runs')
                             line = lines[0]+'1@Runs'+lines[1]
                         output_file.write(line+' 0.5 0.5\n')    
        else:
            shutil.copyfile(self._getFileName('input_particles_m'),self._getFileName('input_particles_m2'))
        params = self._getFileName('input_particles_m2')
        params += ' '+ self._getPath()+'/Particles'
        params += ' --box_size=%d'%(self.inputParticles.get().getDim()[0])+' --create_stack'
                    
        if os.path.exists(self._getPath()+'/Particles'):
            shutil.rmtree(self._getPath()+'/Particles') #remove directory and its contents
        program = eman2.Plugin.getProgram('sxrelion2sphire.py')
        self.runJob(program, params, numberOfMpi=1)

    def processStep(self):
        if self.doResize:
            target_radius = self.target_radius.get()
            target_nx = self.inputParticles.get().getDim()[0]
        else:
            target_radius = self.radius.get()
            target_nx = self.inputParticles.get().getDim()[0]

        program = eman2.Plugin.getProgram('sxisac2.py')
        params = ' Particles/sphire_stack.hdf Class2D' 
        params += ' --radius=%d'%(self.radius.get())
        params += ' --img_per_grp=%d'%(self.numberOfImages.get())
        params += ' --target_radius=%d'% target_radius
        params += ' --target_nx=%d'% target_nx
        params += ' --restart=%d'%(self.restart.get())
        params += ' --thld_err=' + self.thld_err.get()
        if self.doCTF:
            params += ' --CTF'
        if self.doPhase:
            params += ' --VPP'
        if self.extraParams.hasValue():
            params += ' ' + self.extraParams.get()
        
        print params
        self.runJob(program, params, cwd=self._getPath())


    
    def createOutputStep(self):
        if self.doBeautify:
            params = self._getFileName('out_particles')+" "+self._getFileName('out_db')
            program = eman2.Plugin.getProgram('e2proc2d.py')
            self.runJob(program, params, numberOfMpi=1)
            params = "--adjust_to_analytic_model --stack="+ self._getFileName('out_db') + " --isac_dir=" + self._getFileName('isac_dir') + " --output_dir="+ self._getPath()+"/Class_Beau" + " --pixel_size="+str(self.inputParticles.get().getSamplingRate())+ " --radius="+str(self.radius.get())
            if self.doCTF == False:
                params += ' --noctf'
            program = eman2.Plugin.getProgram('sxcompute_isac_avg.py')
            self.runJob(program, params)

        if self.doBeautify:
            print(os.getcwd())
            proc = eman2.Plugin.createEmanProcess(script='save_class.py', args=self._getFileName('class_average_b')+" "+self._getFileName('out_particles')+" "+self._getFileName('notprocessfile')+" "+self._getFileName('params')+" "+self._getFileName('params2')+" "+self._getPath())
            proc.wait()
            self._loadClassesInfo(self._getFileName("out_class"))
        else:
            proc = eman2.Plugin.createEmanProcess(script='save_class.py', args=self._getFileName('class_average')+" "+self._getFileName('out_particles')+" "+self._getFileName('notprocessfile')+" "+self._getFileName('params')+" "+self._getFileName('params2')+" "+self._getPath())
            proc.wait()
            self._loadClassesInfo(self._getFileName("out_class"))

        classes = np.load(self._getPath()+"/classes.npy")
        classes = classes.tolist()
        P = np.load(self._getPath()+"/params.npy")
        P = P.tolist()
        
        ids = []
        with open(self._getFileName("processfile"), 'r') as infile:
            for line in infile:
                ids.append(line.split()[0])


        with open(self._getFileName('input_particles_m2'), 'r') as input_file, open(self._getFileName('input_particles_m3'), 'w') as output_file:
            j = 0 #mutex lock
            i = 0 #start
            k = 0
            l = 0
            for line in input_file:
                if line.startswith("_rln"):
                    output_file.write(line)
                    i = i + 1
                elif i == 0:
                    output_file.write(line)
                elif j == 0:
                    output_file.write('_rlnClassNumber #%d\n'%i)
                    output_file.write('_rlnAnglePsi #%d\n'%(i+1))
                    output_file.write('_rlnOriginX #%d\n'%(i+2))
                    output_file.write('_rlnOriginY #%d\n'%(i+3))
                    if str(k) in ids:
                        iid = self._find_in_list_of_list(classes, k)
                        output_file.write(line.rstrip()+' '+str(iid+1)+' '+str(P[l][0])+' '+str(P[l][1])+' '+str(P[l][2])+'\n')
                        l = l+1
                    else:
                        output_file.write(line.rstrip()+' '+str(len(classes)+1)+' 0 '+' 0 '+' 0 '+'\n')
                    j = 1
                else:
                    k = k +1
                    if str(k) in ids:
                        iid = self._find_in_list_of_list(classes, k)
                        output_file.write(line.rstrip()+' '+str(iid+1)+' '+str(P[l][0])+' '+str(P[l][1])+' '+str(P[l][2])+'\n')
                        l = l+1
                    else:
                        output_file.write(line.rstrip()+' '+str(len(classes)+1)+' 0 '+' 0 '+' 0 '+'\n')

        inputParticles = self.inputParticles.get()

        classes2DSet = self._createSetOfClasses2D(inputParticles)
        self._fillClassesFromLevel(classes2DSet)
  
        self._defineOutputs(outputClasses=classes2DSet)
        self._defineSourceRelation(self.inputParticles, classes2DSet)

    #--------------------------- INFO functions -------------------------------
    def _validate(self):
        errors = []

        return errors

    def _summary(self):
        summary = []
        if not hasattr(self, 'outputClasses'):
            summary.append("Output classes not ready yet.")
        else:
            summary.append("Input Particles: %s" % self.getObjectTag('inputParticles'))
            summary.append("Classified into *%d* classes." % (int(self._getInputParticles().getSize())/self.numberOfImages.__int__()))
            summary.append("Output set: %s" % self.getObjectTag('outputClasses'))

        return summary

    def _methods(self):
        methods = "We classified input particles %s (%d items) " % (
            self.getObjectTag('inputParticles'),
            self._getInputParticles().getSize())
        methods += "into %d classes using sxisac2.py " % (int(self._getInputParticles().getSize())/self.numberOfImages.__int__())
        return [methods]
    
    # --------------------------- UTILS functions ------------------------------
    def _getInputParticles(self):
        return self.inputParticles.get()

    def _loadClassesInfo(self, filename):
        """ Read some information about the produced 2D classes
        from the metadata file.
        """
        self._classesInfo = {}  # store classes info, indexed by class id

        mdClasses = md.MetaData(filename)

        for classNumber, row in enumerate(md.iterRows(mdClasses)):
            index, fn = relionToLocation(row.getValue(md.MDL_IMAGE))
            # Store info indexed by id, we need to store the row.clone() since
            # the same reference is used for iteration
            self._classesInfo[classNumber + 1] = (index, fn, row.clone())
        self._numClass = index

    def _find_in_list_of_list(self, mylist, char):
        for sub_list in mylist:
            if char in sub_list:
                return (mylist.index(sub_list))
        return -1

    def _fillClassesFromLevel(self, clsSet):
        """ Create the SetOfClasses2D from a given iteration. """
        xmpMd = self._getFileName("input_particles_m3") #the particle with orientation parameters (all_parameters)
        clsSet.classifyItems(updateItemCallback=self._updateParticle,
                             updateClassCallback=self._updateClass,
                             itemDataIterator=md.iterRows(xmpMd,
                                                          sortByLabel=md.MDL_ITEM_ID)) # relion style after sort?
    def _updateParticle(self, item, row):
        item.setClassId(row.getValue(md.RLN_PARTICLE_CLASS))
        item.setTransform(rowToAlignment(row, em.ALIGN_2D))

        
    def _updateClass(self, item):
        classId = item.getObjId()
        if classId in self._classesInfo:
            index, fn, row = self._classesInfo[classId]
            item.setAlignment2D()
            item.getRepresentative().setLocation(index, fn)
   

