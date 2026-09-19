# Research Intelligence

Bantu agent menyelidiki topik SEBELUM membuat keputusan atau mengimplementasikan solusi.
Tujuannya: menghasilkan informasi yang akurat, relevan, dan actionable — bukan sekadar menebak.

## When To Use

Gunakan skill ini saat:

- User meminta untuk meneliti sesuatu.
- Informasi terkini mungkin telah berubah.
- Butuh dokumentasi atau spesifikasi teknis.
- Perlu membandingkan beberapa solusi.
- Agent tidak punya cukup bukti untuk keputusan yang andal.
- Project membutuhkan teknologi yang tidak familiar.

JANGAN meneliti berlebihan untuk tugas sederhana yang jawabannya sudah diketahui.

## Research Workflow

### 1. Understand

Identifikasi:

- Apa yang perlu dijawab?
- Keputusan apa yang harus diambil?
- Informasi apa yang sebenarnya dibutuhkan?
- Constraint apa yang dimiliki user?

Hindari meneliti informasi yang tidak relevan.

### 2. Gather

Prefer sumber otoritatif.

Untuk riset teknis, prioritaskan:

1. Official documentation
2. Official repositories
3. Standards / specifications
4. Maintainer documentation
5. High-quality technical references

Gunakan sumber komunitas bila memberikan pengalaman praktis yang berguna, tapi verifikasi klaim penting.

### 3. Cross-Check

Untuk informasi penting:

- Bandingkan beberapa sumber.
- Cek tanggal publikasi/update.
- Cari informasi yang konflik.
- Pisahkan fakta dari opini.
- JANGAN anggap snippet pencarian sebagai bukti definitif.

### 4. Evaluate

Untuk setiap solusi yang mungkin, pertimbangkan:

- Correctness
- Compatibility
- Complexity
- Security
- Performance
- Maintenance
- Cost
- Dependencies
- Project constraints

### 5. Apply

Riset harus berujung pada kesimpulan yang actionable.

JANGAN sekadar buang hasil pencarian.

Jelaskan:

```
Finding
  ↓
Evidence
  ↓
Implication
  ↓
Recommendation
```

### 6. Verify

Sebelum finalisasi:

- Verifikasi klaim teknis penting.
- Cek bahwa API/fitur yang direkomendasikan benar-benar ada.
- Cek kompatibilitas versi bila relevan.
- Identifikasi ketidakpastian.

JANGAN pernah mengarang dokumentasi, API, command, atau capability.

## Research Depth

### Quick
Untuk pertanyaan sederhana.
```
Question → Find reliable answer → Verify → Respond
```

### Standard
Untuk memilih antara solusi.
```
Question → Gather sources → Compare → Evaluate → Recommend
```

### Deep
Untuk keputusan arsitektur/teknis kompleks.
```
Problem → Research → Multiple sources → Cross-check → Compare alternatives
        → Identify tradeoffs → Recommendation → Implementation plan
```

## Output

Bila riset bermakna, struktur hasil sebagai:

```
## Finding
<kesimpulan utama>

## Evidence
- ...
- ...

## Options
### Option A
Pros:
Cons:

### Option B
Pros:
Cons:

## Recommendation
<opsi terbaik dan alasannya>

## Risks / Unknowns
- ...
```

Jaga output proporsional dengan permintaan user.

## Rules

- JANGAN fabrikasi sumber.
- JANGAN fabrikasi fakta.
- JANGAN klaim sesuatu telah diverifikasi bila tidak.
- Prefer primary sources.
- Bedakan informasi terkini dari informasi historis.
- Nyatakan ketidakpastian secara jelas.
- JANGAN over-research masalah sederhana.
- JANGAN mencampuradukkan popularitas dengan kebenaran.
- JANGAN ikuti buta hasil pencarian pertama.

## Coding Research

Saat meneliti masalah coding:

1. Identifikasi teknologi dan versinya.
2. Cek official documentation.
3. Cek kompatibilitas.
4. Temukan implementasi yang direkomendasikan.
5. Cek known limitations.
6. TEST pendekatan yang diusulkan bila memungkinkan.
7. Baru implementasikan.

## Final Principle

Riset ada untuk memperbaiki keputusan, bukan untuk menghasilkan lebih banyak teks.

Agent harus meneliti hanya sebatas yang perlu untuk membuat keputusan yang andal.
