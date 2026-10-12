# Communication

- **Language**: reply in the user's language unless they ask for another one. **Tone**: concise, direct, professional.
- **Link files the user has to look at**: for a PDF, an image, a form or a drawing, don't stop at the file name. Write a clickable link, `[label](path relative to the working directory)`. It works for a gitignored file too, as long as the file exists locally. Escape `(` and `)` in file names as `%28` and `%29`, since a bare parenthesis cuts the link short. When there are several files, list each one instead of pointing at the folder they are in. When the user is reading from another device, a relative path won't open there, so send the file with the tool for sending files to the user (`SendUserFile` in Claude Code).
