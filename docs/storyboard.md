# Storyboard — сценарии переходов состояний (32)

Принцип: каждое эмодзи — мини-сценарий смены состояний, а не статичная картинка
с глоу. Мультисостояния генерим отдельными иконками (gen_states) и склеиваем
движком sequence (crossfade / wipe / glitch_cut), 72-90 кадров, бесшовный луп.

## Мультисостояния (генерим доп. картинки)
- eyes:    [открытые глаза] -> [закрытые] — crossfade (моргание)
- lock:    [открытый замок] -> [закрытый] — wipe (защёлкивание)
- download:[стрелка вниз] -> [галочка] — glitch_cut (загрузка->готово)
- on/off:  on:[тусклая точка]->[яркая+кольцо]; off:[вкл]->[выкл/схлоп] — wipe/glitch
- monitor: [тёмный экран] -> [скан-строки] -> [контент] — wipe (CRT-загрузка)
- rocket:  [на земле] -> [взлёт с пламенем] — crossfade + embers (диагональ)
- ahah:    [улыбка рот закрыт] -> [хохот рот открыт] — crossfade (смех)
- heart:   [контур] -> [залит] — beat-морф (наполнение)
- fire:    [пламя A]->[B]->[C] — crossfade (живой огонь)
- skull:   [челюсть закрыта]->[открыта] — glitch (пиратский, костёр-глаза)
- terminal:[>]->[> set]->[> set_] — text_states, type-in (набор)
- update:  [стрелки 0deg]->[120]->[240] — rotate/sequence (рефреш)
- brain:   [спокойный]->[активные доли светятся] — crossfade (мысль)
- hacker:  [поза набора A]->[B] — glitch (печатает)
- warning: [треугольник]->[яркая вспышка] — strobe/sequence
- think:   [.]->[..]->[...] — text_states (думает)

## Одно состояние + деформация (без доп. генерации)
db,new,doc: assemble (сборка из блоков) | shield,signal,lock-ring: shock_ring
globe,helix,key(диаг): spin3d | palette: color_cycle2
apple,windows,android,ios,penguin: impulse (дыхание формы + пакет)
star: ember_breath (искры)

## Тайминг
hold 0.55-0.75 на состояние, переход eased BRAND, n=72-90 (2.4-3с), 30fps.
