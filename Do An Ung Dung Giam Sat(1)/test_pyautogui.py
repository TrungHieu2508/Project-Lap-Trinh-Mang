import sys
import traceback
try:
    import pyautogui
    from PIL import Image
except Exception as e:
    print('Import error:', e)
    traceback.print_exc()
    sys.exit(2)

def main():
    try:
        size = pyautogui.size()
        print(f"Screen size: {size.width}x{size.height}")

        # Take a screenshot and save it next to the script
        out = 'pyautogui_test_screenshot.png'
        print(f"Taking screenshot and saving to: {out}")
        img = pyautogui.screenshot()
        # Ensure it's a PIL Image and save
        if hasattr(img, 'save'):
            img.save(out)
            print('Screenshot saved successfully.')
        else:
            print('Screenshot object does not have save(), type:', type(img))
            sys.exit(3)

    except Exception as e:
        print('Runtime error:', e)
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()
