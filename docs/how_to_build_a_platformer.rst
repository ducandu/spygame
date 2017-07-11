How to build a Platformer
=========================

In this tutorial, we will be building a 2D platformer from scratch using the spygame library.

[image]

You will need the following software and files to follow along with the different steps:

- The "Tiled" editor to create spygame's level-tmx files. A level-tmx file contains all necessary information for spygame to build a complete level, i.e.
  background and foreground graphics, objects that the level will start with (e.g. player, enemies, traps, elevators, ladders, etc..).
  You can download `Tiled from here <http://www.mapeditor.org>`_.
- The spygame library: See our `Quick Setup Instructions <readme_link.html#get-the-code>`_ for all necessary details on how to get and install spygame.
- Some asset files: Download the following two folders into the directory, in which you would like to develop the game. This will be the directory, in
  which we will write the platformer_2d.py file (the only python file we are going to create and write to in this tutorial).

  a) images/ (`from here <https://github.com/sven1977/spygame/tree/master/examples/platformer_2d/images>`_)
  b) data/ (create this as an empty directory, we'll be populating it from scratch with a level-tmx and several tsx (spygame SpriteSheet) files)

Level tmx-files
---------------

Our first step in building a platformer will be to create the level as a so called level-tmx file. A level-tmx file is a regular tmx file that can be opened and edited
with the Tiled editor, but that also abides to certain spygame specific requirements. Let's start by opening the Tiled editor.

We click on *File->New*

[image]


We specify our tile settings: 24x24 tiles (with 16x16 px each tile)

[image]


This is what our empty level should now look like:

[image]


We click on *File->Save As* and store the newly created tmx file in our project folder, where we already have the images/ folder nicely set up.

Layers
------

It's time to add our first layer to our level. A layer is a group of tiles that all have a common purpose and that - if the layer is visible - get rendered at
the same time. The most commonly used layers in a level are "collision layer", "background layer", and "foreground layer". The collision layer is usually not
visible (not rendered), the background layer usually gets rendered first, followed by the game objects (the player, enemies, etc..) and the foreground
layer, which gets rendered last (so it's in the foreground). Let's start with the collision layer.

The Collision Layer
+++++++++++++++++++

The collision layer defines the location of walls and floors of our level. The players - and usually also the enemies - will collide with the single tiles
of this layer and thus cannot cross the barriers defined by it. This is where we will start: We will paint the floors and walls that make up our level.

We click on *Map->New Tileset* and then on the *Browse* button to select an image that we will turn into a tileset.

[image]

A tileset is simply an image file that can be further split (horizontally and vertically) into "tiles". For example:

[image]

From the images/ folder in our project, we now select the generic.png file and click on *Open*.

We will leave the *Tile width/height* settings at 16px each (this will be the size of all our tiles used for layers in this level) and click on *OK*.

[image]

**Important Note:** For the following, make sure you have the
*View->Views and Toolbars->Tilesets, Objects, Layers, Properties, Main Toolbar, and Tools* all checked to be able to see your new tileset (and some
other things we need later) in the editor.
The tileset we are about to create and setup is a generic tileset that we will use to build our collision layer.
Tiles in this layer will usually not be rendered in the game and only exist for informational purposes.


Modifying Tilesets and Adding Properties to Single Tiles
********************************************************

Next, we will add some properties to some of the tiles in the "generic" tileset so that spygame can recognize these tiles as proper collision tiles
and make sure its physics engine gets the idea of walls, floors and slopes.

If you right click on a tile, you can select *Tile Properties* and then you see in the Properties panel that the tile already has the fixed properties
ID, width and height. Width and height should both be 16. We won't really care about the ID property.

[image]

We right click on the full red square tile and then click on the plus symbol in the properties panel to add a new custom property. We will call the
property *slope* and set its type to *float* and its value to *0.0*. We add another property called *offset* (*float*) and set its value to *1.0*. These two
values basically describe the slope function for that tile. The slope function returns a y value (vertical axis) for each x-axis (horizontal axis) value.
For a fully filled tile, this would be y=0x+1, where o is the slope (no slope, no change in y dependent on x) and an offset (y-axis intersection) of 1.
A 45° up-slope would therefore have the values slope=1.0 and offset=0.0 (y=x). A 45° down-slope will have slope=-1 and offset=1 (y=-x+1), etc..
This way, we are able to define any arbitrary slopes.

We will later add custom properties also to the other tiles in the *generic* tileset, but for now, the fully filled red square will be enough to get us started.

Press *B* to activate the stamp brush tool (make sure the red square tile is still selected in the "generic" tileset).
Paint a floor at the bottom of the level just like this:

[image]

Then paint a wall, some stairs, a hole and other structures like this:

[image]

Finally, we will rename our collision layer into "collision" by double-clicking on the layer in the Layers panel. Also, we need to let spygame know that
the layer is a collision layer. Therefore, we will create a custom property on the layer itself (not on any tiles in a tileset!). We single click on the
"collision" layer in the Layers panel and then on the plus symbol in the then showing layer properties in the Properties panel. This adds a new custom property
to the layer. We will call the property "type" (string) and give it a value of "default".
The type property for layers (as well as - later - objects), determines the collision behavior or our spygame game objects. And "default" here just means,
well, normal, like a wall or a floor are normal things to collide with. We will later get to know the types "friendly", "one_way_platform", "dockable",
"particle" and many other custom ones that we can define (and combine with each other) ourselves.

And this concludes our collision layer. Next, we'll add some nicer background and foreground graphics to our level.

The Background Layer
++++++++++++++++++++

Let's do the background layer next.

We click on *Layer->New->Tile Layer* and rename the newly created layer in the Layer panel to be called "background". This time, we will not add a "type"
property to the layer as the type will default to "none" (or 0), which means the layer won't be considered for any collisions. However, we do need to
set the "do_render" (bool) property and set it to true (tick the box next to the newly created property):

[image]

We also need to specify a "render_order" (int) property and we will set that to 10 to make it render quite early. The "do_render" tells spygame that
a layer should be rendered (the default for layers is false (remember the collision layer, which was not rendered and where we didn't have to set anything)).
The "render_order" is just an int that defines the order in which a renderd layer object should be rendered. The lower the render_order, the earlier the
object gets rendered. Values can be chosen freely, but should - to stick to some convention - be between 0 and 100.



The Foreground Layer
++++++++++++++++++++


The Object Layer
++++++++++++++++


Writing a Class in spygame
--------------------------


