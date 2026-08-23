"""
This Program is used to take snippit of 3d model
and show it in phil widget
uses freecad gui to take screen shot
and then display it in the widget

and snippit is dispossed after exit / creation of new snippet
"""

# importing nessary modules
import subprocess
from pathlib import Path

from voice_input.Keys.config import free_cad_cmd, ai_gen_folder


# snippet preview file location
snippet_path = ai_gen_folder / "preview.png"

snippet_script = ai_gen_folder / "_gen_thumbnail.py"


# creating a function for generate snippet
def generate_snippet():
    # this program snaps snippet of the model in viewport
    # and saves it in the snippet_path
    # for preview in the widget
    # then gets removed after widget is closed

    # 1.create snippet script
    # Use raw strings and escape single quotes to prevent path injection
    safe_folder = str(ai_gen_folder).replace("'", "\\'")
    safe_path = str(snippet_path).replace("'", "\\'")
    snippet_script_content = f"""
import FreeCAD as App
import Part
import FreeCADGui

App.loadFile('{safe_folder}/model.step')
doc = App.activeDocument()
FreeCADGui.showMainWindow()
FreeCADGui.updateGui()
view = FreeCADGui.activeDocument().activeView()
view.viewIsometric()
view.fitAll()
view.saveImage('{safe_path}', 400, 300, '#1a1a1a')
print("Thumbnail saved")
"""
        
    # 2. generating a throw away script
    with open(snippet_script, 'w') as file:
        file.write(snippet_script_content)
    
    # 3.running the script
    try:
        result = subprocess.run(
            [free_cad_cmd, str(snippet_script)],
            capture_output=True,
            text=True,
            timeout=30
        )

        if snippet_path.exists():
            print(f"[Thumbnail] Snapshot saved at: {snippet_path}")
            return snippet_path
        else:
            print(f"[Thumbnail]: Failed to generate Snippet")
            print(f"Error: {result.stderr}")
            return None
    # handles the exception
    except subprocess.TimeoutExpired:
        print("[Thumbnail]: Snippet generation timed out")
        return None
    
    # finally runs even everything fails
    # creating a disposable logic
    finally:
        # throw the script after use
        if snippet_script.exists():
            snippet_script.unlink()
            print("Script removed!")
    
# fetching snippet from above funciton
def get_snippet():
    ''' check if thumbnail exists , used by phil widget to display thumbnail
    '''
    if snippet_path.exists():
        print("Snippet exists!")
        return snippet_path
