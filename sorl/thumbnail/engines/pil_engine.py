from sorl.thumbnail.engines.base import EngineBase
from sorl.thumbnail.compat import BufferIO

try:
    from PIL import Image, ImageFile, ImageDraw, ImageChops, ImageFilter
except ImportError:
    import Image, ImageFile, ImageDraw, ImageChops


def round_corner(radius, fill):
    """Draw a round corner"""
    corner = Image.new('L', (radius, radius), 0)  # (0, 0, 0, 0))
    draw = ImageDraw.Draw(corner)
    draw.pieslice((0, 0, radius * 2, radius * 2), 180, 270, fill=fill)
    return corner


def round_rectangle(size, radius, fill):
    """Draw a rounded rectangle"""
    width, height = size
    rectangle = Image.new('L', size, 255)  # fill
    corner = round_corner(radius, 255)  # fill
    rectangle.paste(corner, (0, 0))
    rectangle.paste(corner.rotate(90),
                    (0, height - radius))  # Rotate the corner and paste it
    rectangle.paste(corner.rotate(180), (width - radius, height - radius))
    rectangle.paste(corner.rotate(270), (width - radius, 0))
    return rectangle


class GaussianBlur(ImageFilter.Filter):
    name = "GaussianBlur"

    def __init__(self, radius=2):
        self.radius = radius

    def filter(self, image):
        return image.gaussian_blur(self.radius)


class Engine(EngineBase):
    def get_image(self, source):
        buffer = BufferIO(source.read())
        return Image.open(buffer)

    def get_image_size(self, image):
        return image.size

    def get_image_info(self, image):
        return image.info or {}

    def is_valid_image(self, raw_data):
        buffer = BufferIO(raw_data)
        try:
            trial_image = Image.open(buffer)
            trial_image.verify()
        except Exception:
            return False
        return True

    def _cropbox(self, image, x, y, x2, y2):
        return image.crop((x, y, x2, y2))

    def _orientation(self, image):
        try:
            exif = image._getexif()
        except (AttributeError, IOError, KeyError, IndexError):
            exif = None

        if exif:
            orientation = exif.get(0x0112)

            if orientation == 2:
                image = image.transpose(Image.FLIP_LEFT_RIGHT)
            elif orientation == 3:
                image = image.rotate(180)
            elif orientation == 4:
                image = image.transpose(Image.FLIP_TOP_BOTTOM)
            elif orientation == 5:
                image = image.rotate(-90).transpose(Image.FLIP_LEFT_RIGHT)
            elif orientation == 6:
                image = image.rotate(-90)
            elif orientation == 7:
                image = image.rotate(90).transpose(Image.FLIP_LEFT_RIGHT)
            elif orientation == 8:
                image = image.rotate(90)

        return image

    def _flip_dimensions(self, image):
        try:
            exif = image._getexif()
        except (AttributeError, IOError, KeyError, IndexError):
            exif = None

        if exif:
            orientation = exif.get(0x0112)
            return orientation in [5, 6, 7, 8]

        return False

    def _colorspace(self, image, colorspace):
        if colorspace == 'RGB':
            if image.mode == 'RGBA':
                return image  # RGBA is just RGB + Alpha
            if image.mode == 'P' and 'transparency' in image.info:
                return image.convert('RGBA')
            return image.convert('RGB')
        if colorspace == 'GRAY':
            return image.convert('L')
        return image

    def _scale(self, image, width, height):
        return image.resize((width, height), resample=Image.ANTIALIAS)

    def _crop(self, image, width, height, x_offset, y_offset):
        return image.crop((x_offset, y_offset,
                           width + x_offset, height + y_offset))

    def _rounded(self, image, r):
        i = round_rectangle(image.size, r, "notusedblack")
        image.putalpha(i)
        return image

    def _blur(self, image, radius):
        return image.filter(GaussianBlur(radius))

    def _padding(self, image, geometry, options):
        x_image, y_image = self.get_image_size(image)
        left = int((geometry[0] - x_image) / 2)
        top = int((geometry[1] - y_image) / 2)
        color = options.get('padding_color')
        im = Image.new(image.mode, geometry, color)
        im.paste(image, (left, top))
        return im

    def _get_raw_data(self, image, format_, quality, image_info=None, progressive=False):
        # Increase (but never decrease) PIL buffer size
        ImageFile.MAXBLOCK = max(ImageFile.MAXBLOCK, image.size[0] * image.size[1])
        bf = BufferIO()

        params = {
            'format': format_,
            'quality': quality,
            'optimize': 1,
        }

        params.update(image_info)

        raw_data = None

        if format_ == 'JPEG' and progressive:
            params['progressive'] = True
        try:
            # Do not save unnecessary exif data for smaller thumbnail size
            params.pop('exif', {})
            image.save(bf, **params)
        except (IOError, OSError):
            # Try without optimization.
            params.pop('optimize')
            image.save(bf, **params)
        else:
            raw_data = bf.getvalue()
        finally:
            bf.close()

        return raw_data
