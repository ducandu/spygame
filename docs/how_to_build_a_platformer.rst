How to build a Platformer
=========================

In this tutorial, we will be building a 2D platformer from scratch using the spygame library. You will need the following software and files to follow along
with the different steps:

- The "Tiled" editor to create spygame's level-tmx files. A level-tmx file contains all necessary information for spygame to build a complete level, i.e.
  background and foreground graphics, objects that the level will start with (e.g. player, enemies, traps, elevators, ladders, etc..).
  You can download `Tiled from here <http://www.mapeditor.org>`_.
- The spygame library: See `Quick Setup Instructions <readme_link.html#get-the-code>`_ for all necessary details on how to get and install spygame.
- Some asset files: Download the following two folders into the directory, in which you would like to develop the game. This will be the directory, in
  which we will write the platformer_2d.py file (the only file we are going to edit in this tutorial).

  a) images/ (`from here <>`_)
  b) data/ (create this as an empty directory, we'll be populating it from scratch with one level-tmx and several tsx (spygame SpriteSheet) files)

Level tmx-files
---------------

Layers
------

The Collision Layer
+++++++++++++++++++

Background and Foreground Layers
++++++++++++++++++++++++++++++++

The Object Layer
++++++++++++++++


Writing a Class in spygame
--------------------------


