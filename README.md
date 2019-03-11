# scipion-em-sphire
Plugin to use Sphire programs within the Scipion framework 

So far we have implemented:
    
* crYOLO Version 1.2.2

Installation  
============ 

1. Please follow installation instructions from [Sphire webpage](http://sphire.mpg.de/wiki/doku.php?id=downloads:cryolo_1&redirect=1) in order to install
 - crYOLO (last tested version: 1.2.2)
 - crYOLO's boxmanager (last tested version: 1.1.0).

2. If you want to use the generic model, please download also the General PhosaursNet model and

   edit the `~/.config/scipion/scipion.conf` file in such a way that exists the following
    ```
    CRYOLO_GEN_MODEL = path/to/the/downloaded/General_PhosaursNet_model 
    ```
3. Install scipion-em-sphire as a Scipion plugin
  
  a) by running:
  ``scipion installp -p scipion-em-sphire``
  
  OR
  
  b) through the GUI menu bar by launching Scipion and Configuration -> Plugins 
   

 * For **developers** replace point 3 for

3a. Clone this repository in a local folder
```
git clone https://github.com/scipion-em/scipion-em-sphire
```

3b. Install the Scipion plugin in a devel mode
```
scipion installp -p --devel /path/where/you/cloned/the/repo/in/the/previous/point
```
    
