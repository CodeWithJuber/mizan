# Basar: images in a chat

Attach a picture to a chat message and MIZAN shows it to the model with that
message. It can answer about the picture, read text in it, or build a web page
from a design ("Design an HTML page for this and preview it").

## What happens to an image

1. **Checked.** The web app sends the image with the chat message
   (`images` on `POST /api/chat/stream`: at most 4 images, each at most
   10 MB). MIZAN decodes it with Pillow. Only PNG, JPEG, WebP and GIF are
   accepted; a GIF is read as its first frame.
   - Anything else is refused with a 400 before anything runs.
   - So is an image with more than 40 million pixels (a decompression bomb).
2. **Cleaned.** The image is re-encoded, which drops its metadata. EXIF
   holds the camera, the time and often the **GPS position** where a photo
   was taken; none of it reaches the model or the disk.
3. **Scaled.** The image is scaled down to at most 1568 px on its longer
   side; beyond that, models see no more detail and only cost more.
   - Images with transparency stay PNG; the rest become JPEG.
4. **Kept with the chat.** It is stored in the owner's own folder,
   `$MIZAN_DATA_DIR/media/<first 24 hex characters of the SHA-256 of the
   owner's id>/`, and named by its SHA-256.
   - The user's message records which images it carried, never the image
     itself. The request receipt does the same.
   - `GET /api/media/{sha}` returns only the owner's own images.
   - The chat shows the images again when it is reopened.
5. **Shown to the model** for the turn it was sent in and for the next turn.
   That way a follow-up such as "Image ka HTML banana tha" still sees the
   picture; a turn after that does not.
   - Each provider gets the image in its own form: Anthropic image blocks,
     or `image_url` data parts for OpenAI-compatible providers.
   - MIZAN's own recipes include it too. For example, the project recipe's
     Lisan prompts see the design it is building from.
6. **Counted in spending.** Iqtisad bounds each image at 1,600 input tokens
   before the call is admitted.
7. **Erased with the chat.** Deleting the chat (Mahw) deletes its images,
   unless another of the owner's chats shows the same picture.

## A page from a picture, or words about it

Fahm reads the message as usual; an attached image changes nothing in how the
request is understood. "Design an HTML page for this and preview it" and "Image
ka html banana tha" are `build_project` requests, so MIZAN's project recipe
builds the page in a workspace and shows the preview. Its Lisan prompts carry
the picture. "What is in this picture?" is conversation: the chat model answers
in words, looking at the image. Both kinds are seeds in
`tadbir/data/qasd/intents.tsv`.

## Text inside an image is outside content

A picture can carry written instructions ("ignore your rules and…"). MIZAN
treats it like outside content, but an image alone no longer holds an action:
as for a page, a model-chosen change needs a person's approval only after Amanah
found an instruction in what the run read ([amanah.md](amanah.md)).

## Limits

- Images go with the web chat. Telegram photos are not read yet.
- The model must accept image input; OpenRouter's catalog says which do
  (`input_modalities`, kept with the model limits).
  - On a turn with an image, Lisan (Wazn) chooses only among the listed
    models that read images.
  - A model the catalog marks as text-only gets a note in place of the
    picture saying it was not seen, so it says so instead of guessing.
  - A model the catalog does not know gets the image.
- Audio attachments still use the older media connection. For speech, use
  the microphone (Sama').

Before this, an attached image was sent to an older perception engine that
returned keywords ("Core concepts: …"). It never reached a model and was not
kept in the chat.
