import os
import cv2
import time
import piexif
from PIL import Image, ImageDraw, ImageFont
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pymediainfo import MediaInfo
from datetime import datetime
import sys
import traceback

# --- Constantes ---
VIDEO_EXTENSIONS = (
    '.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv', '.webm', '.mpeg', '.mpg',
    '.m4v', '.3gp'
)
OUTPUT_SUBFOLDER_NAME = "Miniature"
FONT_SIZE = 75
TEXT_COLOR = (255, 255, 255)
TEXT_OUTLINE_COLOR = (0, 0, 0)

# --- Fonction pour le chemin des ressources (pour PyInstaller) ---
def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

FONT_PATH = resource_path("arial.ttf")

# --- Fonctions utilitaires Tkinter (pour robustesse) ---
def show_tk_dialog(dialog_type, title, message, **kwargs):
    # Cette fonction crée et détruit sa propre racine pour chaque dialogue modal.
    # C'est acceptable pour les dialogues ponctuels.
    root_dialog = tk.Tk()
    root_dialog.withdraw()
    root_dialog.attributes('-topmost', True) # Essayer de mettre les dialogues au premier plan
    result = None
    if dialog_type == "filedialog.askdirectory":
        result = filedialog.askdirectory(title=title, parent=root_dialog, **kwargs)
    elif dialog_type == "messagebox.showinfo":
        messagebox.showinfo(title, message, parent=root_dialog, **kwargs)
    elif dialog_type == "messagebox.showerror":
        messagebox.showerror(title, message, parent=root_dialog, **kwargs)
    elif dialog_type == "messagebox.showwarning":
        messagebox.showwarning(title, message, parent=root_dialog, **kwargs)
    
    # S'assurer que la fenêtre est bien détruite
    if root_dialog.winfo_exists():
        root_dialog.destroy()
    return result

# --- Fonctions du script ---
def select_folder(title="Sélectionnez le dossier contenant les vidéos"):
    return show_tk_dialog("filedialog.askdirectory", title, None)

def get_video_file_time_info(video_path):
    timestamp = None
    used_fallback_to_os_stat = True
    current_time_val = time.time()
    formatted_date = time.strftime('%Y:%m:%d %H:%M:%S', time.localtime(current_time_val))
    timestamp = current_time_val
    media_info_date_str = None
    parsed_dt_from_metadata = None
    try:
        media_info = MediaInfo.parse(video_path)
        possible_date_fields = ['recorded_date', 'creation_date', 'encoded_date', 'tagged_date']
        for track in media_info.tracks:
            if media_info_date_str: break
            for field_name in possible_date_fields:
                if hasattr(track, field_name):
                    value = getattr(track, field_name)
                    if value:
                        media_info_date_str = str(value)
                        break # Trouvé, on sort de la boucle des champs
            if media_info_date_str: break # Trouvé, on sort de la boucle des pistes
        
        if media_info_date_str:
            if "UTC" in media_info_date_str: media_info_date_str = media_info_date_str.replace("UTC", "").strip()
            target_format = '%d/%m/%Y %H:%M'
            alternative_formats = ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M:%S.%f']
            all_formats_to_try = [target_format] + alternative_formats
            for fmt in all_formats_to_try:
                try:
                    date_part_to_parse = media_info_date_str.split('.')[0]
                    fmt_part_to_use = fmt.split('.')[0]
                    parsed_dt_from_metadata = datetime.strptime(date_part_to_parse, fmt_part_to_use)
                    break
                except ValueError:
                    try:
                        parsed_dt_from_metadata = datetime.strptime(media_info_date_str, fmt)
                        break
                    except ValueError: continue
            if parsed_dt_from_metadata:
                timestamp = parsed_dt_from_metadata.timestamp()
                formatted_date = parsed_dt_from_metadata.strftime('%Y:%m:%d %H:%M:%S')
                used_fallback_to_os_stat = False
    except Exception:
        pass 
    if used_fallback_to_os_stat:
        try:
            stat_info = os.stat(video_path)
            timestamp = stat_info.st_mtime
            formatted_date = time.strftime('%Y:%m:%d %H:%M:%S', time.localtime(timestamp))
        except Exception:
            pass
    return timestamp, formatted_date, used_fallback_to_os_stat

# --- Fonction principale logique ---
def main_logic():
    # Créer une racine principale pour cette session de l'application.
    # Elle sera parente de la fenêtre de statut et détruite proprement.
    app_root = tk.Tk()
    app_root.withdraw() # Cacher cette racine, elle ne sert que de parent.

    status_window = None # Initialiser pour le bloc finally

    try:
        video_folder = select_folder() # Utilise sa propre racine temporaire via show_tk_dialog
        if not video_folder:
            show_tk_dialog("messagebox.showinfo", "Information", "Aucun dossier sélectionné. Sortie du programme.")
            return # Sortie de main_logic, app_root sera détruite dans finally

        output_folder = os.path.join(video_folder, OUTPUT_SUBFOLDER_NAME)
        try:
            os.makedirs(output_folder, exist_ok=True)
        except OSError as e:
            show_tk_dialog("messagebox.showerror", "Erreur", f"Erreur lors de la création du dossier de sortie '{output_folder}': {e}")
            return # Sortie, app_root sera détruite

        font = None
        try:
            font = ImageFont.truetype(FONT_PATH, FONT_SIZE)
        except IOError:
            show_tk_dialog("messagebox.showwarning", "Avertissement Police",
                           f"Police '{FONT_PATH}' non trouvée. Utilisation d'une police par défaut.")
            font = ImageFont.load_default()
        font_loaded = (font is not None and hasattr(font, 'getbbox'))


        video_files_to_process = []
        for item_name in os.listdir(video_folder):
            item_path = os.path.join(video_folder, item_name)
            if os.path.isfile(item_path) and item_name.lower().endswith(VIDEO_EXTENSIONS):
                video_files_to_process.append(item_name)
        
        total_videos_found = len(video_files_to_process)
        if total_videos_found == 0:
            summary_message_text = f"Aucun fichier vidéo compatible trouvé dans :\n{video_folder}"
            show_tk_dialog("messagebox.showinfo", "Résumé du traitement", summary_message_text)
            return # Sortie, app_root sera détruite

        # --- Fenêtre d'avancement, parentée à app_root ---
        status_window = tk.Toplevel(app_root) 
        status_window.title("Avancement...")
        status_window.geometry("450x100")
        status_window.resizable(False, False)
        try:
            status_window.attributes('-topmost', True)
        except tk.TclError: pass # -topmost peut ne pas être supporté partout

        status_label_var = tk.StringVar()
        status_label = tk.Label(status_window, textvariable=status_label_var, padx=10, pady=10, wraplength=430)
        status_label.pack(expand=True, fill=tk.BOTH)
        # --- Fin de la fenêtre d'avancement ---

        miniatures_created_successfully = 0
        date_fallback_count = 0
        videos_failed_to_process = 0
        videos_with_date_fallback = []

        for index, item_name in enumerate(video_files_to_process):
            current_video_num = index + 1
            status_label_var.set(f"Traitement de la vidéo {current_video_num}/{total_videos_found}:\n{item_name}")
            try:
                if status_window.winfo_exists(): # Nécessaire si l'utilisateur ferme la fenêtre d'état
                   status_window.update_idletasks()
            except tk.TclError: # La fenêtre a pu être détruite entre-temps
                break 

            item_path = os.path.join(video_folder, item_name)
            _, creation_date_str, used_media_info_fallback = get_video_file_time_info(item_path)
            
            if used_media_info_fallback:
                date_fallback_count += 1
                videos_with_date_fallback.append(item_name)

            cap = cv2.VideoCapture(item_path)
            if not cap.isOpened():
                videos_failed_to_process += 1
                if cap: cap.release()
                continue
            ret, frame = cap.read()
            if cap: cap.release() # Libérer immédiatement après read()
            if not ret or frame is None:
                videos_failed_to_process += 1
                continue
            try:
                img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            except cv2.error:
                videos_failed_to_process += 1
                continue
            draw = ImageDraw.Draw(img)
            text_position = (15, 15)
            outline_thickness = 2
            active_font = font if font_loaded else ImageFont.load_default() # Utiliser la police chargée ou la police par défaut
            
            # Dessiner le contour
            for x_offset in range(-outline_thickness, outline_thickness + 1):
                for y_offset in range(-outline_thickness, outline_thickness + 1):
                    if x_offset != 0 or y_offset != 0:
                         draw.text((text_position[0] + x_offset, text_position[1] + y_offset),
                                   creation_date_str, TEXT_OUTLINE_COLOR, font=active_font)
            # Dessiner le texte principal
            draw.text(text_position, creation_date_str, TEXT_COLOR, font=active_font)

            thumbnail_filename = f"{os.path.splitext(item_name)[0]}.jpg"
            output_path = os.path.join(output_folder, thumbnail_filename)
            try:
                img.save(output_path, "JPEG")
                exif_dict = {"Exif": {piexif.ExifIFD.DateTimeOriginal: creation_date_str.encode('utf-8'),
                                     piexif.ExifIFD.DateTimeDigitized: creation_date_str.encode('utf-8')}}
                exif_bytes = piexif.dump(exif_dict)
                piexif.insert(exif_bytes, output_path)
                miniatures_created_successfully += 1
            except Exception:
                pass # Erreur de sauvegarde/EXIF

        # Fermeture de la fenêtre d'avancement
        if status_window and status_window.winfo_exists():
            status_window.destroy()
            status_window = None # Réinitialiser

        # Préparation et affichage du résumé
        summary_lines = [
            f"Traitement terminé.",
            f"Dossier source : {video_folder}",
            f"Dossier des miniatures : {output_folder}",
            f"Nombre total de fichiers vidéo trouvés : {total_videos_found}",
            f"Miniatures créées avec succès ✅: {miniatures_created_successfully}",
            f"Vidéos utilisant une date de fallback : {date_fallback_count}",
            f"Vidéos qui n'ont pas pu être traitées : {videos_failed_to_process}"
        ]
        if videos_with_date_fallback:
            summary_lines.append("\nFichiers utilisant une date de fallback :")
            max_files_to_list = 15
            for i, name in enumerate(videos_with_date_fallback):
                if i < max_files_to_list:
                    summary_lines.append(f"- {name}")
                elif i == max_files_to_list:
                    summary_lines.append(f"...et {len(videos_with_date_fallback) - max_files_to_list} autre(s).")
                    break
        summary_message_text = "\n".join(summary_lines)
        show_tk_dialog("messagebox.showinfo", "Résumé du traitement", summary_message_text)

    finally:
        # S'assurer que la fenêtre de statut (si elle existe encore) et app_root sont détruites
        if status_window and status_window.winfo_exists():
            status_window.destroy()
        if app_root and app_root.winfo_exists():
            app_root.destroy()

# --- Wrapper principal pour la gestion globale des erreurs ---
def main():
    try:
        main_logic()
    except Exception as e:
        detailed_error = traceback.format_exc()
        # Vous pouvez écrire detailed_error dans un fichier log si besoin
        # print("Une erreur critique est survenue :\n" + detailed_error) 
        error_message = (f"Une erreur inattendue est survenue et l'application va se fermer.\n\n"
                         f"Détails : {type(e).__name__}: {str(e)}")
        if len(error_message) > 1000:
             error_message = error_message[:1000] + "..."
        show_tk_dialog("messagebox.showerror", "Erreur Critique", error_message)

if __name__ == '__main__':
    main()