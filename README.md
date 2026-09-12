
# GE3 Blender Scene
![Static Badge](https://img.shields.io/badge/Blender-5.0%2B-orange)  ![Static Badge](https://img.shields.io/badge/Versions-1.0.0-blue)  

GE3 Blender Scene is a plugin for blender to import and export mdl models for God Eater 3.  



## Navigation
- [Installation](#installation)
- [Usage](#usage)
- [Credits](#credits)
### Installation

1. Download the repository or the latest release.
2. In Blender, go to Edit > Preferences > Add-ons > Install from disk.
3. Select the .zip file.
4. Enable God Eater 3 Mdl in the add-ons list.
    
### Usage

This tool works fully within blender, being able to import and export a fully working model.

Importing a model will create a new collection, Scene root empty and whatever skeleton and models that are stored within the mdl. While the collection and Scene root are not vital to the exporting their names are used within the file so it's best to keep them.

GE3 also stores vital shader information within it's models, this information will be stored in the materials created on import, it can be viewed in the new God Eater 3 panel in the Main 3D view under the N Menu.

Exporting models can require some prep work:  
- Weights are limited to 4 bones per vert, this can be managed using blenders "Limit Total" and "Normalize all" options in weight painting.  
- Vertex Colors are stored in Vertex - Byte Color.  
- Shape normals are best handled by spliting the edge (Read about the include geo nodes below).  
- UV Islands need be on split edges (Read about the include geo nodes below).  
- Materials MUST have GE3 shader info, any material without this will be skipped.
- Meshes can only use one material.
- A models attributes are defined by their Shader, IE you can't add vertex colours to a shader that doesn't support them, they will be ignored on Export.

With all that out of the way, i've included some export options to help with clean exporting.  

First is the "Use Face Split Fix", on export a special geo node will be apply to split edges on their UV island boundary and and egdes marked sharp. This geo node can only be added to a model before exporting and you can customize options from there. If the geo nodes are on a model being exporting the modifier will be used instead of temp one being applied.  

Second the "Separate Objects by Material" will split up your objects so they're one material per if they have multiple.


#### Supported Models
- PC and Nintendo Switch models are supported for Importing. Only PC models are supported for Export.
- Face Morphs Importing and Exporting.
- Static models should be supported but not well tested.
- Body Models, Hair Models, and Face Models tested on Import and Export
### Credit
Xentax - The original data_fate_extella_ge3 script for Noesis served as a starting point for me research.  
