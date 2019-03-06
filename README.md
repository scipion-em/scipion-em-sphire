# scipion-em-sphire
Plugin to use Sphire programs within the Scipion framework 

So far we have implemented:
    
* crYOLO Version 1.2.2

Installation  
============ 

1. Please follow installation instructions at <http://sphire.mpg.de/wiki/doku.php?id=downloads:cryolo_1&redirect=1>

2. Install `crYOLO Version 1.2.2 <http://sphire.mpg.de/wiki/doku.php?id=cryolo_archive#cryolo>

3. Install `crYOLO boxmanager 1.1.0 <http://sphire.mpg.de/wiki/doku.php?id=cryolo_archive#cryolo>

4. If you want to use the generic model, please download the General PhosaursNet model and it the add the path in  
    ~/.config/scipion/scipion.conf
    CRYOLO_GEN_MODEL = path/to/the/downloaded/General_PhosaursNet_model 

5. git clone the plugin repository to any local folder <https://github.com/scipion-em/>
   git clone git@github.com:scipion-em/scipion-em-myplugin.git /home/me/myplugin
    
6. Install scipion-em-sphire
  a) In user mode: or through the GUI menu bar 
  ``scipion installp -p scipion-em-sphire``
  
  OR
  
  b, through the GUI menu bar. Please select Configuration/Plugins 
   
7. Add the path to ~/.config/scipion/scipion.conf 
    CRYOLO_HOME = ~/anaconda3/envs/cryolo
   
    
    