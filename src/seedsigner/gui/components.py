import math
import os
import pathlib

from dataclasses import dataclass
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from seedsigner.models import Singleton



# TODO: Remove all pixel hard coding
EDGE_PADDING = 8
COMPONENT_PADDING = 8

TOP_NAV_TITLE_FONT_SIZE = 19
BODY_FONT_NAME = "OpenSans-Regular"
BODY_FONT_SIZE = 17
BODY_LINE_SPACING = 0.25

BUTTON_FONT_NAME = "OpenSans-SemiBold"
BUTTON_FONT_SIZE = 18



def calc_text_centering(font: ImageFont,
                        text: str,
                        is_text_centered: bool,
                        box_width: int,
                        box_height: int,
                        start_x: int = 0,
                        start_y: int = 0):
    # see: https://pillow.readthedocs.io/en/stable/handbook/text-anchors.html#text-anchors
    offset_x, offset_y = font.getoffset(text)
    (box_left, box_top, box_right, box_bottom) = font.getbbox(text, anchor='lt')
    ascent, descent = font.getmetrics()

    # print(f"----- {text} -----")
    # print(f"offset_x, offset_y: ({offset_x}, {offset_y})")
    # print(f"(box_left, box_top, box_right, box_bottom): ({box_left}, {box_top}, {box_right}, {box_bottom})")
    # print(f"ascent, descent: ({ascent}, {descent})")

    if is_text_centered:
        text_x = int((box_width - (box_right - offset_x)) / 2) - offset_x
    else:
        text_x = COMPONENT_PADDING

    text_y = int((box_height - (ascent - offset_y)) / 2) - offset_y

    return (start_x + text_x, start_y + text_y)



class Fonts(Singleton):
    font_path = os.path.join(pathlib.Path(__file__).parent.resolve(), "..", "resources", "fonts")
    fonts = {}

    @classmethod
    def get_font(cls, font_name, size):
        # Cache already-loaded fonts
        if font_name not in cls.fonts:
            cls.fonts[font_name] = {}

        if size not in cls.fonts[font_name]:
            cls.fonts[font_name][size] = ImageFont.truetype(os.path.join(cls.font_path, f"{font_name}.ttf"), size)

        return cls.fonts[font_name][size]



class BaseComponent:
    def __post_init__(self):
        from seedsigner.gui import Renderer
        self.renderer = Renderer.get_instance()


    def render(self):
        raise Exception("render() not implemented in the child class!")



@dataclass
class TextArea(BaseComponent):
    """
        Not to be confused with an html <textarea>! This is a rect-delimited text
        display box that could be the main body content of a screen or a sub-zone
        of text within a more complicated page.

        Auto-calcs line breaks based on input text and font (somewhat naive; only
        breaks on spaces. Future enhancement could break on hyphens, too).

        Raises an Exception if the text won't fit in the given rect.

        Attrs with defaults must be listed last.
    """
    text: str     # display value
    width: int
    height: int = 0    # 0 = special case: autosize to min height
    screen_x: int = 0
    screen_y: int = 0
    background_color: str = "black"
    font_name: str = BODY_FONT_NAME
    font_size: int = BODY_FONT_SIZE
    font_color: str = "#fcfcfc"
    is_text_centered: bool = True
    supersampling_factor: int = 2


    def __post_init__(self):
        super().__post_init__()
        self.font = Fonts.get_font(self.font_name, int(self.supersampling_factor * self.font_size))
        self.supersampled_width = self.supersampling_factor * self.width
        self.supersampled_height = self.supersampling_factor * self.height
        self.line_spacing = int(BODY_LINE_SPACING * self.font_size)

        # We have to figure out if and where to make line breaks in the text so that it
        #   fits in its bounding rect (plus accounting for edge padding) using its given
        #   font.
        tw, self.text_height = self.font.getsize(self.text)

        # Stores each line of text and its rendering starting x-coord
        self.text_lines = []
        self.text_width = 0
        def _add_text_line(text, width):
            if self.is_text_centered:
                text_x = int((self.supersampled_width - width) / 2)
            else:
                text_x = self.supersampling_factor * EDGE_PADDING
            self.text_lines.append({"text": text, "text_x": text_x})

            if width > self.text_width:
                self.text_width = width

        if tw < self.supersampled_width - (2 * EDGE_PADDING * self.supersampling_factor):
            # The whole text fits on one line
            _add_text_line(self.text, tw)

            if self.height == 0:
                self.text_y = 0
                self.supersampled_height = self.text_height
            else:
                # Vertical starting point calc is easy in this case
                self.text_y = int(((self.supersampling_factor * self.supersampled_height) - self.text_height) / 2)

        else:
            # Have to calc how to break text into multiple lines
            def _binary_len_search(min_index, max_index):
                # Try the middle of the range
                index = math.ceil((max_index + min_index) / 2)
                if index == 0:
                    # Handle edge case where there's only one word in the last line
                    index = 1

                tw, th = self.font.getsize(" ".join(words[0:index]))

                if tw > self.supersampled_width - (2 * EDGE_PADDING * self.supersampling_factor):
                    # Candidate line is still too long. Restrict search range down.
                    if min_index + 1 == index:
                        # There's no room left to search
                        index -= 1
                    return _binary_len_search(min_index, index)
                elif index == max_index:
                    # We have converged
                    return (index, tw)
                else:
                    # Candidate line is possibly shorter than necessary.
                    return _binary_len_search(index, max_index)

            words = self.text.split(" ")
            while words:
                (index, tw) = _binary_len_search(0, len(words))
                _add_text_line(" ".join(words[0:index]), tw)
                words = words[index:]

            total_text_height = self.text_height * len(self.text_lines) + self.line_spacing * (len(self.text_lines) - 1)
            if self.height > 0 and total_text_height > self.supersampled_height + 2 * COMPONENT_PADDING * self.supersampling_factor:
                raise Exception("Text cannot fit in target rect with this font/size")
            else:
                self.supersampled_height = total_text_height

            # Vertically center the text's starting point
            self.text_y = int((self.supersampled_height - total_text_height) / 2)

        # Make sure the width/height that get referenced outside this obj are
        #   restored to their normal scaling factor.
        self.width = int(self.supersampled_width / self.supersampling_factor)
        self.height = int(self.supersampled_height / self.supersampling_factor)
        self.text_width = int(self.text_width / self.supersampling_factor)


    def render(self):
        if self.supersampling_factor > 1:
            # Render to a temp img scaled up by self.supersampling_factor, then resize down
            #   with bicubic resampling.
            img = Image.new("RGB", (self.supersampled_width, self.supersampled_height), self.background_color)
            draw = ImageDraw.Draw(img)
            cur_y = self.text_y
        else:
            draw = self.renderer.draw
            cur_y = self.text_y + self.screen_y

        for line in self.text_lines:
            draw.text((line["text_x"], cur_y), line["text"], fill=self.font_color, font=self.font)
            cur_y += self.text_height + self.line_spacing

        if self.supersampling_factor > 1:
            resized = img.resize((self.width, self.height), Image.LANCZOS)
            resized = resized.filter(ImageFilter.SHARPEN)
            self.renderer.canvas.paste(resized, (self.screen_x, self.screen_y))



@dataclass
class Button(BaseComponent):
    # TODO: Rename the seedsigner.helpers.Buttons class (to Inputs?)
    """
        Attrs with defaults must be listed last.
    """
    text: str     # display value
    screen_x: int
    screen_y: int
    width: int
    height: int
    icon_name: str = None   # Optional icon to accompany the text
    icon_y_offset: int = 2
    is_icon_inline: bool = True    # True = render next to text; False = render centered above text
    text_y_offset: int = 0
    background_color: str = "#2c2c2c"
    selected_color: str = "orange"
    font_name: str = BUTTON_FONT_NAME
    font_size: int = BUTTON_FONT_SIZE
    font_color: str = "#fcfcfc"
    selected_font_color: str = "black"
    is_text_centered: bool = True
    is_selected: bool = False


    def __post_init__(self):
        super().__post_init__()

        self.font = Fonts.get_font(self.font_name, self.font_size)

        if self.text:
            (self.text_x, self.text_y) = calc_text_centering(
                font=self.font,
                text=self.text,
                is_text_centered=self.is_text_centered,
                box_width=self.width,
                box_height=self.height - self.text_y_offset,
                start_x=self.screen_x,
                start_y=self.screen_y + self.text_y_offset
            )
        elif self.icon_name and self.is_icon_inline:
            self.text_x = self.screen_x + int(self.width / 2)
            self.text_y = self.screen_y + int(self.height / 2)

        # Preload the icon and its "_selected" variant
        if self.icon_name:
            icon_padding = 8
            dirname = os.path.dirname(__file__)
            icon_url = os.path.join(dirname, "..", "..", "seedsigner", "resources", "icons", self.icon_name)
            self.icon = Image.open(icon_url + ".png").convert("RGB")
            self.icon_selected = Image.open(icon_url + "_selected.png").convert("RGB")

            if self.is_icon_inline:
                if self.text:
                    if self.is_text_centered:
                        # Shift the text's centering
                        self.text_x += int((self.icon.width + icon_padding) / 2)
                    else:
                        self.text_x += self.icon.width + icon_padding
                self.icon_x = self.text_x - (self.icon.width + icon_padding)
                self.icon_y = self.text_y + self.icon_y_offset
            else:
                self.icon_x = self.screen_x + int((self.width - self.icon.width) / 2)
                self.icon_y = self.screen_y + self.icon_y_offset


    def render(self):
        if self.is_selected:
            background_color = self.selected_color
            font_color = self.selected_font_color
        else:
            background_color = self.background_color
            font_color = self.font_color

        self.renderer.draw.rounded_rectangle((self.screen_x, self.screen_y, self.screen_x + self.width, self.screen_y + self.height), fill=background_color, radius=COMPONENT_PADDING)

        if self.text:
            self.renderer.draw.text((self.text_x, self.text_y), self.text, fill=font_color, font=self.font)

        if self.icon_name:
            icon = self.icon
            if self.is_selected:
                icon = self.icon_selected
            self.renderer.canvas.paste(icon, (self.icon_x, self.icon_y))



@dataclass
class IconButton(Button):
    """
        A button that is primarily a big icon (e.g. the Home screen buttons) w/text below
        the icon.
    """
    is_icon_inline: bool = False
    icon_y_offset: int = 8



@dataclass
class TopNav(BaseComponent):
    text: str
    width: int
    height: int
    background_color: str = "black"
    font_name: str = "OpenSans-SemiBold"
    font_size: int = TOP_NAV_TITLE_FONT_SIZE
    font_color: str = "#fcfcfc"
    show_back_button: bool = True
    show_power_button: bool = False
    is_selected: bool = False


    def __post_init__(self):
        super().__post_init__()
        self.font = Fonts.get_font(self.font_name, self.font_size)
        button_width = 32

        if self.show_back_button:
            self.back_button = IconButton(
                text=None,
                icon_name="back",
                screen_x=EDGE_PADDING,
                screen_y=EDGE_PADDING,
                width=button_width,
                height=button_width,
                icon_y_offset=4,
            )

        if self.show_power_button:
            self.power_button = IconButton(
                text=None,
                icon_name="power",
                screen_x=self.width - button_width - EDGE_PADDING,
                screen_y=EDGE_PADDING,
                width=button_width,
                height=button_width,
                icon_y_offset=4,
            )

        # if not self.font:
        #     # Pre-calc how much room the title bar text will take up. Use the biggest font
        #     #   that will fit.
        #     max_font_width = self.width - (2 * self.back_button.width) - (4 * EDGE_PADDING)
        #     for font in Fonts.ASSISTANT_BOLD:
        #         self.text_width, self.text_height = font.getsize(self.text)
        #         if self.text_width < max_font_width:
        #             self.font = font
        #             self.text_x = int((self.width - self.text_width) / 2)
        #             self.text_y = int((self.height - self.text_height) / 2)
        #             break

        # else:
        (self.text_x, self.text_y) = calc_text_centering(
            font=self.font,
            text=self.text,
            is_text_centered=True,
            box_width=self.width,
            box_height=self.height,
            start_x=0,
            start_y=0
        )


    @property
    def selected_button(self):
        from seedsigner.gui.screens import BaseScreen
        if not self.is_selected:
            return None
        if self.show_back_button:
            return BaseScreen.RET_CODE__BACK_BUTTON
        if self.show_power_button:
            return BaseScreen.RET_CODE__POWER_BUTTON


    def render(self):
        self.renderer.draw.rectangle((0, 0, self.width, self.height), fill=self.background_color)
        if self.show_back_button:
            self.back_button.is_selected = self.is_selected
            self.back_button.render()
        if self.show_power_button:
            self.power_button.is_selected = self.is_selected
            self.power_button.render()

        self.renderer.draw.text((self.text_x, self.text_y), self.text, fill=self.font_color, font=self.font)



