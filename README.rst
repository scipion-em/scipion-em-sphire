====================
Sphire scipion plugin
====================

Plugin to use Sphire programs within the Scipion framework 

So far we have implemented:
    
* crYOLO Version 1.2.2

=====
Setup
=====

- **Please follow installation instructions** from [Sphire webpage](http://sphire.mpg.de/wiki/doku.php?id=downloads:cryolo_1&redirect=1) in order to install:
   - crYOLO (last tested version: 1.2.2)
   - crYOLO's boxmanager (last tested version: 1.1.0).

- **If you want to use the generic model**, please download also the General PhosaursNet model and

   edit the  ~/.config/scipion/scipion.conf file in such a way that exists the following
   
.. code-block::

    CRYOLO_GEN_MODEL = path/to/the/downloaded/General_PhosaursNet_model 
   

- **Install scipion-em-sphire as a Scipion plugin**
  

.. code-block::
  
      scipion installp -p scipion-em-sphire
 
  OR
  
  - through the plugin manager GUI by launching Scipion and following *Configuration* >> *Plugins* 
   
Alternatively, in devel mode:

.. code-block::

    scipion installp -p local/path/to/scipion-em-sphire --devel
    
