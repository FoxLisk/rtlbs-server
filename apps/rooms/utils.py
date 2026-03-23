import os.path
import tempfile

from django.core.files import File


def _save_uploaded_image(rt, uploaded_f, ext):
    rt.media.save(uploaded_f.name, File(uploaded_f), save=False)


def _save_uploaded_video(rt, uploaded_f, ext):
    if ext != 'mp4':
        stored_f = tempfile.NamedTemporaryFile(suffix='.' + ext)
        stored_f.write(uploaded_f.read())
        stored_f.flush()

        converted_f = tempfile.NamedTemporaryFile(suffix='.mp4')

        ret = os.system("""
            ffmpeg -i "{fname_in}" \
                -c:v libx264 \
                -preset slow \
                -crf 18 \
                -bf 2 \
                -flags +cgop \
                -pix_fmt yuv420p \
                -sws_flags neighbor \
                -s:v 512x448 \
                -c:a aac \
                -b:a 160k \
                -movflags faststart \
                -y \
                "{fname_out}"
        """.format(fname_in=stored_f.name, fname_out=converted_f.name))
        assert ret == 0, ret
        filename = uploaded_f.name.rsplit('.', 1)[0] + '.mp4'
    else:
        converted_f = uploaded_f
        filename = uploaded_f.name

    rt.media.save(filename, File(converted_f), save=False)


def save_uploaded_media(rt, f):
    filename = os.path.basename(f.name).lower()
    if '.' not in filename:
        raise Exception('No extension?')

    ext = filename.rsplit('.', 1)[-1]

    if ext in 'jpg|jpeg|png|bmp|gif'.split('|'):
        _save_uploaded_image(rt, f, ext)
    elif ext in 'webm|mkv|flv|vob|ogg|ogv|avi|mov|wmv|mp4|m4p|m4v|mpg|mp2|mpeg|mpv'.split('|'):
        _save_uploaded_video(rt, f, ext)
    else:
        raise Exception('Unknown extension')
