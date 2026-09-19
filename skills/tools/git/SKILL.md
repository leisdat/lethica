# Git

## Purpose
Version control dan kolaborasi kode.

## Workflow

1. status (cek state)
2. diff (cek perubahan)
3. stage (pilih file)
4. commit (pesan jelas)
5. pull / push (sync)

## Rules

- Pesan commit deskriptif, bukan "fix" atau "update".
- Jangan commit secret / credential.
- Jangan force push ke branch utama tanpa alasan.
- Pisahkan perubahan logis ke commit berbeda bila memungkinkan.
- Cek status sebelum add . besar-besaran.

## Common

- branch: buat branch fitur, jangan langsung ke main
- merge / rebase: pahami perbedaan
- stash: simpan pekerjaan belum selesai
- log: telusuri history

## Avoid

- commit tanpa diff review
- force push public branch
- mix unrelated changes in one commit
- ignore .gitignore
