# MiniatureGooglePhoto
Create a preview picture of a video with is date to save larges videos on a second Googles account but knowing there is a video at this date.

Demande un dossier, liste les vidéos (extensions courantes), puis crée un sous-dossier Miniature.

Pour chaque vidéo :

Extrait une date depuis les métadonnées via pymediainfo (sinon “fallback” sur la date système).

Lit la première frame avec OpenCV, la convertit en image PIL et dessine la date dessus (texte blanc + léger contour noir).

Sauvegarde en JPEG dans Miniature et écrit les tags EXIF DateTimeOriginal/DateTimeDigitized.

Affiche une petite fenêtre d’avancement et, à la fin, un résumé (créées, échecs, fichiers ayant utilisé le fallback).
