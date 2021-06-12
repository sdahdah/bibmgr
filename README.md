# bibmgr

CLI reference management tools for BibTeX.

Relies heavily on [biblib](https://github.com/aclements/biblib).

## Sample Config

Default location is `$XDG_CONFIG_HOME/.config/bibmgr/bibmgr.conf` on Linux
(where `$XDG_CONFIG_HOME` is usually just `~`) and
`%LOCALAPPDATA%/bibmgr/bibmgr.conf` on Windows.

```
[config]
default_library=library
filename_length=100
key_length=20
wrap_width=80

[library]
bibtex_file=/path/to/bibliography.bib
storage_path=/path/to/linked/file/storage/
default_group=unfiled
```

# To Do

- [ ] Fix renaming files with dots in the name? Or is that ok?
- [ ] Clean up folders and files not referenced by bibtex?
- [ ] Find a way to do clean integration testing with file manipulations
