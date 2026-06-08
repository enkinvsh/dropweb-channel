# Премиум-моушн: плейбук движка (синтез research + librarian)

Цель: заменить детские эффекты (дыхание/сжатие/моргание) на CRT-моушн с
мотивированным импульсом. Топ-3 апгрейда (наибольший прирост качества):
ФОСФОРНАЯ ПЕРСИСТЕНЦИЯ + ИМПУЛЬСНЫЙ ТАЙМИНГ + MULTI-RADIUS BLOOM.

## Базовые правила
- Рендер в супер-разрешении 300x300 -> эффекты -> даунсэмпл в 100x100 (антиалиас).
- Бесшовный луп: фаза p = i/N (НЕ i/(N-1)). Длины: 48/60/72/90 кадров @30fps.
- Один мотивированный «сюжет» на эмодзи: charge -> snap/emit -> phosphor decay -> quiet scan.
- Ядро глифа стабильно и читаемо; двигается СВЕТ (glow/частицы/скан), не сам глиф.
- Все амплитуды крошечные (100px): сдвиг 1-5px, поворот 1-8°, squash 0.94-1.07,
  хром. сдвиг 0.5-2px, частиц 4-18 по 1-3px, трейл 3-8 кадров.

## Кривая бренда
Cubic(0.2,0.8,0.2,1.0), 400ms = 12 кадров @30fps. Сэмплить через Newton (cubic_bezier_y).

## Порядок рендера (на каждый кадр)
1. маска (с reveal/stagger/squash на уровне маски)
2. neon core #00DE52
3. multi-radius additive bloom (r=0.6/1.6/3.5/7.0, alpha 1.0/0.75/0.38/0.18, pulse только в импульсе)
4. фосфорный персистент-буфер (trail*=0.78..0.86; trail=max(trail,bright))
5. частицы/искры с трейлами (только для энергетичных)
6. motion blur (2-3 субкадра) на быстрых фазах
7. хроматическая аберрация (idle 0.2-0.35px, удар 0.8-1.2px на 2-4 кадра)
8. cosine-сканлайны 6-10% + бегущий hum-бар (ролл ровно +100px за луп)
9. (финиш) vignette 18-35%, barrel k~0.035
10. композит на #030305 для превью; экспорт RGBA

## Энкод (VP9 + альфа)
ffmpeg -y -framerate 30 -i f/%03d.png -an -vf "format=yuva420p" \
  -c:v libvpx-vp9 -pix_fmt yuva420p -b:v 0 -crf 32 \
  -deadline good -cpu-used 2 -row-mt 1 -auto-alt-ref 0 out.webm
Если >256КБ: crf 36-42, меньше частиц/шума, 24fps.
(-auto-alt-ref 0 ОБЯЗАТЕЛЕН для альфы.)

## Эффект на каждое из 32 (premium-назначение)
db: staggered disk build + data-scan | new: badge pop (антиципация+оувершут)
on: crt power snap + afterglow | off: power-down glitch (схлоп по Y + chroma)
brain: secondary neural pulse (лобы со стаггером) | shield: elastic impact + ring
think: thought-node orbit/pulse | monitor: raster boot reveal + roll
palette: assemble color cells + color_cycle | helix(диаг): strand build + twist
signal: radiating rings | globe: longitude scan (без full-spin)
doc: CRT wipe/type lines | download: anticipated drop + motion blur
penguin: idle voltage (eyes secondary) | apple: static shimmer + edge sweep
windows: 4-pane stagger light-on | android: antenna/eye follow-through
ios: clean device shimmer | update: segmented circular rebuild (rotate)
rocket(диаг): launch anticip + ember trail + blur | fire: ember energy + flame stagger
ahah: controlled laughter bounce | skull: ominous glitch hit + eye flicker
hacker: terminal glitch/type hybrid + sparks | terminal: type-in + cursor secondary
lock: shackle snap/settle + impact bloom | key(диаг): turn/twist follow-through
eyes: pupil lead + eyelid follow | heart: voltage pulse (не дыхание)
star: sharp twinkle assemble + sparks | warning: alert impact/glitch hybrid

## Источники (для воспроизведения)
CRT: libretro crt-lottes-fast.glsl, Swordfish90/cool-retro-term, blurbusters/crt-beam-simulator
ffmpeg: lagfun(decay 0.78-0.88) афтерглоу, lenscorrection(k1) бочка, vignette, tblend/tmix трейлы, gblur
