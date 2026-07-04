// ============================================================================
// Граф знаний R&D — горно-металлургическая отрасль (Норникель)
// Датасет собран вручную на основе реального корпуса «Источники информации»
// (Яндекс.Диск, кейс «Научный клубок»), папка «Обзоры» — 13 документов ОИП/ТИ/ИС
// Института Гипроникель, 2016–2025 гг. Каждый узел Publication/Experiment/Finding
// несёт поле source с точным именем исходного файла для верификации.
// ============================================================================

const GROUPS = {
  Material:    {color:{background:'#ff9f0a', border:'#c77800'}},
  Process:     {color:{background:'#30d158', border:'#1f9e40'}},
  Equipment:   {color:{background:'#64d2ff', border:'#0a84ff'}},
  Property:    {color:{background:'#5e5ce6', border:'#3634a3'}},
  Condition:   {color:{background:'#ffd60a', border:'#c7a300'}},
  Experiment:  {color:{background:'#bf5af2', border:'#8e3fc0'}},
  Publication: {color:{background:'#8e8e93', border:'#636366'}},
  Expert:      {color:{background:'#ff375f', border:'#c22a48'}},
  Facility:    {color:{background:'#ac8e68', border:'#7a6449'}},
  Finding:     {color:{background:'#ff453a', border:'#c2352c'}}
};

const G_RU = {
  Material:'Материал', Process:'Процесс', Equipment:'Оборудование',
  Property:'Свойство', Condition:'Условие', Experiment:'Эксперимент',
  Publication:'Публикация', Expert:'Эксперт', Facility:'Предприятие',
  Finding:'Вывод'
};

const ET_RU = {
  USES_MATERIAL:'Использует материал', OPERATES_AT_CONDITION:'При условии',
  PRODUCES_OUTPUT:'Производит', DESCRIBED_IN:'Описано в', VALIDATED_BY:'Подтверждено',
  CONTRADICTS:'Противоречит', HAS_PROPERTY:'Имеет свойство', USES_EQUIPMENT:'Использует оборудование',
  AUTHORED_BY:'Автор', WORKS_AT:'Работает в', PART_OF:'Часть', MENTIONS:'Упоминает',
  APPLIES_TO:'Применимо к'
};

const NODES = [];
const EDGES = [];
const PROPS = {};

function N(id, label, group, props){
  NODES.push({id, label, group, shape:'dot'});
  PROPS[id] = props || {};
}
function E(from, type, to){ EDGES.push({from, to, type}); }

// ── Эксперты (носители экспертизы) ──────────────────────────────────────────
N('exp_tsymbulov','Л.Б. Цымбулов','Expert',{name:'Л.Б. Цымбулов', role:'Директор Департамента по исследованиям и разработкам', org:'Институт Гипроникель', geography:'RU', confidence:'подтверждено', source:'титульные листы ОИП 2022–2025'});
N('exp_kozyrev','С.М. Козырев','Expert',{name:'С.М. Козырев', role:'Директор Департамента по исследованиям и разработкам, к.г.-м.н.', org:'Институт Гипроникель', geography:'RU', confidence:'подтверждено', source:'титульные листы ОИП/ТИ/ИС 2016–2018'});
N('exp_kuznetsov','Р.А. Кузнецов','Expert',{name:'Р.А. Кузнецов', role:'Начальник ОИП (отдела информационных проектов)', org:'Институт Гипроникель', geography:'RU', confidence:'подтверждено', source:'все документы ОИП/ТИ/ИС 2016–2025'});
N('exp_evgrafova','А.К. Евграфова','Expert',{name:'А.К. Евграфова', role:'Главный специалист, соавтор большинства обзоров', org:'Институт Гипроникель', geography:'RU', confidence:'подтверждено', source:'все обзоры ОИП 2018–2025'});
N('exp_podokhanova','С.В. Подоханова','Expert',{name:'С.В. Подоханова', role:'Ведущий специалист / специалист 1-й категории', org:'Институт Гипроникель', geography:'RU', confidence:'подтверждено', source:'ТИ-05-2017, ОИП-02-2025, ОИП-07-2024, ОИП-07-2022'});
N('exp_taskinen','Pekka Taskinen','Expert',{name:'Pekka Taskinen', role:'Профессор, руководитель исследований равновесий штейн/шлак', org:'Университет Аалто, Финляндия', geography:'world', confidence:'подтверждено', source:'Avarmaa et al. 2015, 2016'});
N('exp_avarmaa','Katri Avarmaa','Expert',{name:'Katri Avarmaa', role:'Исследователь равновесного распределения драгметаллов', org:'Университет Аалто, Финляндия', geography:'world', confidence:'подтверждено', source:'Avarmaa et al. 2015, 2016; Piskunen et al. 2018'});
E('exp_evgrafova','WORKS_AT','fac_giproniсkel');
E('exp_kuznetsov','WORKS_AT','fac_giproniсkel');
E('exp_podokhanova','WORKS_AT','fac_giproniсkel');
E('exp_tsymbulov','WORKS_AT','fac_giproniсkel');
E('exp_taskinen','WORKS_AT','fac_aalto');

N('fac_giproniсkel','ООО «Институт Гипроникель»','Facility',{name:'ООО «Институт Гипроникель»', kind:'НИИ, R&D-центр Норникеля', geography:'RU', city:'Санкт-Петербург', confidence:'подтверждено', source:'титульные листы всех документов корпуса'});
N('fac_aalto','Университет Аалто','Facility',{name:'Университет Аалто (Aalto University)', kind:'Университет, лаборатория металлургии', geography:'world', city:'Финляндия', confidence:'подтверждено', source:'ОИП-06-2018 (список литературы)'});

// ══════════════════════════════════════════════════════════════════════════
// КЛАСТЕР A — Электроэкстракция никеля и меди (запрос 2 кейса)
// ══════════════════════════════════════════════════════════════════════════
N('pub_a1','Электроэкстракция никеля. Влияние состава электролита (ОИП-09-2023)','Publication',{name:'Электроэкстракция никеля. Влияние состава электролита', code:'ОИП – 09 – 2023', date:'2023', author:'А.К. Евграфова', geography:'world', confidence:'подтверждено', source:'Обзоры/Электроэкстракция никеля. Влияние состава электролита.docx'});
N('pub_a2','Обзор технических решений в области электролитического производства никеля и меди (ОИП-03-2025)','Publication',{name:'Обзор технических решений в области электролитического производства никеля и меди', code:'ОИП – 03 – 2025', date:'2025', author:'А.К. Евграфова', geography:'world', confidence:'подтверждено', source:'Обзоры/Обзор технических решений в области электролитического производства никеля и меди.docx'});
E('pub_a1','AUTHORED_BY','exp_evgrafova'); E('pub_a2','AUTHORED_BY','exp_evgrafova');

N('mat_ni_cathode','Никелевые катоды высокой чистоты','Material',{name:'Никелевые катоды высокой чистоты', kind:'Металлопродукция', purity:'>99,98–99,99% Ni', confidence:'подтверждено', geography:'world', source:'pub_a1'});
N('mat_electrolyte_cl','Хлоридный электролит никеля','Material',{name:'Хлоридный никелевый электролит (NiCl2)', kind:'Технологический раствор', composition:'Ni 60–95 г/л, Cl 60 г/л, pH 1,4–2,0', confidence:'подтверждено', geography:'world', source:'pub_a1, pub_a2'});
N('mat_electrolyte_so4','Сульфатный электролит никеля','Material',{name:'Сульфатный никелевый электролит (NiSO4)', kind:'Технологический раствор', composition:'Ni 80–125 г/л, pH 2–4', confidence:'подтверждено', geography:'world', source:'pub_a1, pub_a2'});
N('mat_boric_acid','Борная кислота (H3BO3)','Material',{name:'Борная кислота', kind:'Добавка к электролиту', role:'буфер, повышает катодную поляризацию', dose:'6–10 г/л', confidence:'подтверждено', geography:'world', source:'pub_a1'});
N('mat_sls','Додецилсульфат натрия (SLS/ДСН)','Material',{name:'Додецилсульфат натрия', kind:'ПАВ-добавка', role:'снижает поверхностное натяжение, устраняет питтинг', dose:'10–40 мг/л', confidence:'подтверждено', geography:'world', source:'pub_a1'});
N('mat_na2so4','Сульфат натрия (Na2SO4)','Material',{name:'Сульфат натрия', kind:'Добавка/примесь электролита', dose:'до 155,9 г/л', confidence:'подтверждено', geography:'world', source:'pub_a1'});

for(const [id,label,def] of [
 ['proc_ew_cl','Электроэкстракция никеля из хлоридного раствора','Промышленно применяется на Nikkelverk (Норвегия) и Niihama (Япония) свыше 30 лет; выход по току выше, чем в сульфатном варианте, ниже поляризация'],
 ['proc_ew_so4','Электроэкстракция никеля из сульфатного раствора','«Зрелая» технология; ниже коррозия, дешевле аноды (Pb-сплавы), но ниже допустимая плотность тока (200–240 А/м2)'],
]) N(id,label,'Process',{name:label, definition:def, confidence:'подтверждено', geography:'world', source:'pub_a1, pub_a2'});

N('proc_emew','Технология EMEW (цилиндрическая ячейка)','Process',{name:'EMEW', definition:'Коаксиальная цилиндрическая ячейка с высокоскоростной прокачкой электролита; позволяет вести процесс без диафрагмы благодаря малому времени пребывания раствора (6–15 с)', confidence:'подтверждено', geography:'world', source:'pub_a2'});
N('proc_mettop_brx','Технология параллельных потоков METTOP-BRX','Process',{name:'METTOP-BRX / PFT', definition:'Ввод свежего электролита точно перед поверхностью катода через сопла (УПП/ППП); минимизирует диффузионный погранслой, позволяет поднять плотность тока до 400–420 А/м2', confidence:'подтверждено', geography:'world', source:'pub_a2'});
N('proc_anode_bag','Технология анодных мешков','Process',{name:'Анодные мешки (взамен катодных)', definition:'Разработана Outotec совместно с Norilsk Nickel Harjavalta (2008) и опробована на заводе Rustenburg; позволяет достичь высокой концентрации серной кислоты в анолите (до 80 г/л) без ущерба качеству катодов', confidence:'подтверждено', geography:'world', source:'pub_a2'});

N('eq_diaphragm_cell','Диафрагменная ячейка','Equipment',{name:'Диафрагменная (мембранная) ячейка', kind:'Электролизёр', description:'Катод/анод разделены проницаемой тканевой диафрагмой (катодный или анодный мешок) для контроля переноса H+', confidence:'подтверждено', geography:'world', source:'pub_a1, pub_a2'});
N('eq_emew_cell','Ячейка EMEW','Equipment',{name:'Ячейка EMEW®', kind:'Электролизёр', description:'Анод Ø~50мм (Ti+MeOx), катод Ø~151мм (нерж. сталь, съёмная труба), без диафрагмы', confidence:'подтверждено', geography:'world', source:'pub_a2'});
N('eq_pfd','Устройство параллельного потока (УПП/PFD)','Equipment',{name:'УПП / PFD, ППП / PFP', kind:'Узел ввода электролита', description:'Сопла индивидуального проекта направляют электролит вдоль поверхности катода', confidence:'подтверждено', geography:'world', source:'pub_a2'});

N('cond_catholyte_flow_diaphragm','Скорость циркуляции католита (диафрагменная ячейка)','Condition',{name:'Скорость циркуляции католита', min:20, max:30, unit:'л/ч', context:'обычная скорость движения католита через диафрагму, регулируется разностью уровней католит/анолит', confidence:'подтверждено', geography:'world', source:'pub_a2'});
N('cond_catholyte_feed_pilot','Скорость подачи католита в ячейку (пилот, анодные мешки)','Condition',{name:'Подача католита в ячейку', min:1.5, max:5.0, unit:'м3/ч', context:'пилотные испытания Outotec/Norilsk Nickel Harjavalta; выше скорость → легче контроль pH и выше ΔNi', confidence:'подтверждено', geography:'world', source:'pub_a2'});
N('cond_emew_flow','Скорость потока электролита в EMEW','Condition',{name:'Скорость потока EMEW', min:6, max:10, unit:'м3/ч на ячейку', context:'соответствует 100–167 л/мин, время пребывания 6–15 с', confidence:'подтверждено', geography:'world', source:'pub_a2'});
N('cond_mettop_flow','Циркуляция электролита METTOP-BRX','Condition',{name:'Циркуляция электролита (METTOP-BRX)', min:90, max:100, unit:'л/мин/электролизёр', context:'против 25–45 л/мин в традиционном варианте/Isa — рост почти втрое', confidence:'подтверждено', geography:'world', source:'pub_a2'});
N('cond_current_density_cl','Катодная плотность тока (хлоридный электролиз)','Condition',{name:'Плотность тока, хлоридный электролит', min:233, max:279, unit:'А/м2', confidence:'подтверждено', geography:'world', source:'pub_a1'});
N('cond_current_density_so4','Катодная плотность тока (сульфатный электролиз)','Condition',{name:'Плотность тока, сульфатный электролит', min:200, max:240, unit:'А/м2', confidence:'подтверждено', geography:'world', source:'pub_a1'});
N('cond_temp_electrolysis','Температура электролиза никеля','Condition',{name:'Температура электролита', min:60, max:65, unit:'°C', confidence:'подтверждено', geography:'world', source:'pub_a1'});

N('find_catholyte_optimal','Оптимальная скорость циркуляции католита — 20–30 л/ч (диафрагма)','Finding',{statement:'В типовой диафрагменной ячейке необходимая скорость движения католита сквозь диафрагму обеспечивается регулированием разности уровней электролита и обычно составляет 20–30 л/ч; более высокая скорость рециркуляции облегчает контроль pH и повышает ΔNi.', confidence:'подтверждено', n_sources:2, geography:'world', source:'pub_a2'});
N('find_emew_no_diaphragm','EMEW не требует диафрагмы благодаря высокой скорости потока','Finding',{statement:'Малое время пребывания электролита в ячейке EMEW (6–15 с при скорости 6–10 м3/ч) делает выделение H+ у катода несущественным — диафрагма не нужна, контроль кислотности ведётся вне ячейки.', confidence:'подтверждено', n_sources:1, geography:'world', source:'pub_a2'});
N('find_mettop_tradeoff','METTOP-BRX: рост плотности тока до 400–420 А/м2 ценой перестройки цеха','Finding',{statement:'Параллельный поток электролита у катода позволяет поднять плотность тока на 50% и производительность цеха без ухудшения качества катодов, но требует спецсопел и системы позиционирования катодов.', confidence:'подтверждено', n_sources:1, geography:'world', source:'pub_a2'});
N('find_anode_bag_tradeoff','Плотная vs неплотная диафрагма анодного мешка — компромисс кислотность/pH','Finding',{statement:'Плотная ткань даёт высокую концентрацию кислоты в анолите (124 г/л), но pH католита падает с 3,1 до 1,5 и выход по току снижается до 94%; неплотная ткань стабильнее по pH (3,7→3,1, выход ~100%), но кислота в анолите ниже (28 г/л).', confidence:'подтверждено', n_sources:1, geography:'world', source:'pub_a2'});

E('proc_ew_cl','USES_MATERIAL','mat_electrolyte_cl'); E('proc_ew_so4','USES_MATERIAL','mat_electrolyte_so4');
E('proc_ew_so4','USES_MATERIAL','mat_boric_acid'); E('proc_ew_so4','USES_MATERIAL','mat_sls'); E('proc_ew_so4','USES_MATERIAL','mat_na2so4');
E('proc_ew_cl','PRODUCES_OUTPUT','mat_ni_cathode'); E('proc_ew_so4','PRODUCES_OUTPUT','mat_ni_cathode');
E('proc_ew_cl','USES_EQUIPMENT','eq_diaphragm_cell'); E('proc_ew_so4','USES_EQUIPMENT','eq_diaphragm_cell');
E('proc_emew','USES_EQUIPMENT','eq_emew_cell'); E('proc_emew','PRODUCES_OUTPUT','mat_ni_cathode');
E('proc_mettop_brx','USES_EQUIPMENT','eq_pfd');
E('proc_anode_bag','USES_EQUIPMENT','eq_diaphragm_cell');
E('proc_ew_cl','OPERATES_AT_CONDITION','cond_current_density_cl'); E('proc_ew_so4','OPERATES_AT_CONDITION','cond_current_density_so4');
E('proc_ew_cl','OPERATES_AT_CONDITION','cond_temp_electrolysis'); E('proc_ew_so4','OPERATES_AT_CONDITION','cond_temp_electrolysis');
E('proc_ew_so4','OPERATES_AT_CONDITION','cond_catholyte_flow_diaphragm');
E('proc_anode_bag','OPERATES_AT_CONDITION','cond_catholyte_feed_pilot');
E('proc_emew','OPERATES_AT_CONDITION','cond_emew_flow');
E('proc_mettop_brx','OPERATES_AT_CONDITION','cond_mettop_flow');
E('find_catholyte_optimal','VALIDATED_BY','cond_catholyte_flow_diaphragm'); E('find_catholyte_optimal','DESCRIBED_IN','pub_a2');
E('find_emew_no_diaphragm','VALIDATED_BY','proc_emew'); E('find_emew_no_diaphragm','DESCRIBED_IN','pub_a2');
E('find_mettop_tradeoff','VALIDATED_BY','proc_mettop_brx'); E('find_mettop_tradeoff','DESCRIBED_IN','pub_a2');
E('find_anode_bag_tradeoff','VALIDATED_BY','proc_anode_bag'); E('find_anode_bag_tradeoff','DESCRIBED_IN','pub_a2');
E('pub_a1','MENTIONS','proc_ew_cl'); E('pub_a1','MENTIONS','proc_ew_so4');
E('pub_a2','MENTIONS','proc_emew'); E('pub_a2','MENTIONS','proc_mettop_brx'); E('pub_a2','MENTIONS','proc_anode_bag');

N('fac_nikkelverk','Nikkelverk (Норвегия)','Facility',{name:'Nikkelverk', kind:'Никелерафинировочный завод', owner:'Glencore (ранее Falconbridge)', geography:'world', capacity:'~90 тыс т катодов/год (1980-е)', confidence:'подтверждено', source:'pub_a1, pub_a2'});
N('fac_niihama','Niihama (Япония)','Facility',{name:'Niihama', kind:'Никелерафинировочный завод', owner:'Sumitomo', geography:'world', capacity:'~30 (ранее), ~60 тыс т/г (сейчас)', confidence:'подтверждено', source:'pub_a1, pub_a2'});
N('fac_sandouville','Sandouville (Франция)','Facility',{name:'Sandouville', kind:'Никелерафинировочный завод', owner:'Sybanie-Stillwater (ранее Eramet)', geography:'world', capacity:'12 тыс т/г Ni выс. чистоты', confidence:'предварительно', source:'pub_a1'});
N('fac_harjavalta','Harjavalta (Финляндия)','Facility',{name:'Norilsk Nickel Harjavalta', kind:'Никелерафинировочный завод', owner:'Норникель', geography:'world', confidence:'подтверждено', source:'pub_a2'});
N('fac_rustenburg','Rustenburg (ЮАР)','Facility',{name:'Rustenburg', kind:'Завод базовых металлов', owner:'Anglo Platinum', geography:'world', confidence:'подтверждено', source:'pub_a2'});
N('fac_brixlegg','Brixlegg (Австрия)','Facility',{name:'Brixlegg', kind:'Медерафинировочный завод', owner:'Montanwerke Brixlegg', geography:'world', capacity:'148 тыс т/г Cu (2019)', confidence:'подтверждено', source:'pub_a2'});
N('fac_xiangguang','Xiangguang (Китай)','Facility',{name:'Yanggu Xiangguang Copper', kind:'Медерафинировочный завод', geography:'world', capacity:'500 тыс т/г медеплавильных мощностей', confidence:'подтверждено', source:'pub_a2'});
for(const f of ['fac_nikkelverk','fac_niihama','fac_sandouville']) { E(f,'PART_OF','proc_ew_cl'); }
E('fac_harjavalta','PART_OF','proc_anode_bag'); E('fac_rustenburg','PART_OF','proc_anode_bag');
E('fac_brixlegg','PART_OF','proc_mettop_brx'); E('fac_xiangguang','PART_OF','proc_mettop_brx');

// ══════════════════════════════════════════════════════════════════════════
// КЛАСТЕР B — Распределение Au, Ag, МПГ между штейном и шлаком (запрос 3)
// ══════════════════════════════════════════════════════════════════════════
N('pub_b1','Распределение Au, Ag и МПГ между медным/никелевым штейном и шлаком (ОИП-06-2018)','Publication',{name:'Распределение Au, Ag и МПГ между медным/никелевым штейном и шлаком (по зарубежным источникам последних лет)', code:'ОИП – 06 – 2018', date:'2018', author:'А.К. Евграфова', geography:'world', confidence:'подтверждено', source:'Обзоры/Распределение Au, Ag и МПГ между меднымникелевым штейном и шлаком.docx'});
E('pub_b1','AUTHORED_BY','exp_evgrafova');

N('mat_cu_matte','Медный штейн (Cu2S-FeS)','Material',{name:'Медный штейн', kind:'Промпродукт плавки', composition:'Cu2S-FeS, сортность 50–75% Cu', confidence:'подтверждено', geography:'world', source:'pub_b1'});
N('mat_ni_matte','Никелевый штейн','Material',{name:'Никелевый штейн', kind:'Промпродукт плавки', composition:'маломедистый [Ni]:[Cu]=4, Fe до 15%', confidence:'подтверждено', geography:'world', source:'pub_b1'});
N('mat_fe_silicate_slag','Железосиликатный шлак','Material',{name:'Железосиликатный шлак (FeOx-SiO2)', kind:'Отвальный продукт плавки', confidence:'подтверждено', geography:'world', source:'pub_b1'});
for(const [id,sym,ldesc] of [['mat_au','Au','золото'],['mat_ag','Ag','серебро'],['mat_pt','Pt','платина'],['mat_pd','Pd','палладий'],['mat_rh','Rh','родий']]){
  N(id, sym+' ('+ldesc+')', 'Material', {name:ldesc+' ('+sym+')', kind:'Драгоценный металл, примесный элемент', confidence:'подтверждено', geography:'world', source:'pub_b1'});
}
N('proc_matte_slag_equilibrium','Равновесие штейн/шлак при плавке','Process',{name:'Равновесное распределение элементов штейн/шлак', definition:'Лабораторное установление равновесия штейна и силикатного шлака в контролируемой газовой атмосфере (CO-CO2-SO2-Ar) при 1250–1450°C для определения коэффициентов распределения L=масс.%(штейн)/масс.%(шлак)', confidence:'подтверждено', geography:'world', source:'pub_b1'});
E('proc_matte_slag_equilibrium','USES_MATERIAL','mat_cu_matte'); E('proc_matte_slag_equilibrium','USES_MATERIAL','mat_ni_matte'); E('proc_matte_slag_equilibrium','USES_MATERIAL','mat_fe_silicate_slag');

N('exp_aalto_cu_2015','Равновесие Cu-штейн/шлак 1250–1350°C (Avarmaa 2015)','Experiment',{name:'Equilibrium Distribution of Precious Metals between Slag and Copper Matte at 1250-1350°C', team:'Университет Аалто (Avarmaa, O\'Brien, Taskinen)', method:'тигли из SiO2, электронно-зондовый микроанализ (Cameca SX100) + LA-ICP-MS', date:'2015', geography:'world', confidence:'подтверждено', source:'pub_b1 (цит. K.Avarmaa et al., J.Sustain.Metall. 2015)'});
N('exp_aalto_cu_2016','Распределение Ag,Au,Pd,Pt,Rh медный штейн/шлак (Avarmaa 2016)','Experiment',{name:'Distribution of Precious Metals Between Copper Matte and Iron Silicate Slag', team:'Университет Аалто (Avarmaa, Johto, Taskinen)', method:'метод с подложкой SiO2, ICP-MS', date:'2016', geography:'world', confidence:'подтверждено', source:'pub_b1 (цит. Metallurgical and Materials Transactions B, 2016)'});
N('exp_roghani_2000','Распределение малых элементов Cu-штейн/шлак при высоком pSO2 (Roghani 2000)','Experiment',{name:'Phase Equilibrium and Minor Element Distribution between FeOx-SiO2-MgO Slag and Cu2S-FeS Matte', team:'G.Roghani, Y.Takeda, K.Itagaki', method:'газовая смесь Ar-SO2-S2, выдержка 35ч при 1573К', date:'2000', geography:'world', confidence:'подтверждено', source:'pub_b1 (Metall.Mater.Trans.B, v.31B, 2000)'});
N('exp_piskunen_2018','Распределение МПГ в прямой плавке никелевого штейна (Piskunen 2018)','Experiment',{name:'Precious Metal Distributions in Direct Nickel Matte Smelting with Low-Cu Mattes', team:'P.Piskunen, K.Avarmaa и др.', date:'2018', geography:'world', confidence:'подтверждено', source:'pub_b1 (Metall.Mater.Trans.B, v.49B, 2018)'});
for(const e of ['exp_aalto_cu_2015','exp_aalto_cu_2016','exp_roghani_2000','exp_piskunen_2018']) { E(e,'DESCRIBED_IN','pub_b1'); E(e,'VALIDATED_BY','proc_matte_slag_equilibrium'); }
E('exp_aalto_cu_2015','WORKS_AT','fac_aalto'); E('exp_aalto_cu_2016','WORKS_AT','fac_aalto'); E('exp_piskunen_2018','WORKS_AT','fac_aalto');

N('cond_temp_cu_equilibrium','Температура равновесия Cu-штейн/шлак','Condition',{name:'Температура опытов', min:1250, max:1350, unit:'°C', confidence:'подтверждено', geography:'world', source:'pub_b1'});
N('cond_temp_ni_equilibrium','Температура равновесия Ni-штейн/шлак','Condition',{name:'Температура опытов (никелевый штейн)', min:1350, max:1450, unit:'°C', confidence:'подтверждено', geography:'world', source:'pub_b1'});
N('cond_matte_grade_65','Сортность медного штейна 65% Cu','Condition',{name:'Сортность штейна', value:65, unit:'% Cu', confidence:'подтверждено', geography:'world', source:'pub_b1'});

N('find_L_au_cu','L(Au) штейн/шлак ≈ 1500 при 65% Cu (медный штейн)','Finding',{statement:'При равновесии медный штейн/железосиликатный шлак 1250–1350°C и сортности штейна 65% Cu коэффициент распределения золота Lшт/шл ≈ 1500; зависимость от температуры слабая.', confidence:'подтверждено', n_sources:3, geography:'world', source:'pub_b1'});
N('find_L_pgm_cu','L(Pd)≈3000, L(Pt)≈5000, L(Rh)≈7000-8000 (медный штейн, 65% Cu)','Finding',{statement:'Коэффициенты распределения МПГ между медным штейном и шлаком при 65% Cu в штейне: Pd — ок. 3000, Pt — ок. 5000, Rh — 7000–8000; растворимость в шлаке в типичном случае 5–20 ppm.', confidence:'подтверждено', n_sources:3, geography:'world', source:'pub_b1'});
N('find_L_ag_scatter','L(Ag) 100–200 (Cu-штейн) / 100–400 (Ni-штейн) — большой разброс','Finding',{statement:'Коэффициент распределения серебра существенно более низкий и разбросанный, чем у Au/МПГ: 100–200 для медного штейна и 100–400 для никелевого — разброс объясняется заметным улетучиванием Ag в ходе многочасового установления равновесия.', confidence:'предварительно', n_sources:2, geography:'world', source:'pub_b1'});
N('find_L_au_pt_pd_ni','L(Au)~10^4, L(Pt)~10^5, L(Pd)~10^4 (никелевый штейн, Fe=5%)','Finding',{statement:'Для равновесия маломедистого никелевого штейна ([Ni]:[Cu]=4) со шлаком FeOx-SiO2-MgO при 1350–1450°C и содержании Fe в штейне 5%вес: L(Au)≈10^4, L(Pt)≈10^5, L(Pd)≈10^4 — на 1–2 порядка выше, чем для медного штейна.', confidence:'подтверждено', n_sources:2, geography:'world', source:'pub_b1'});
E('find_L_au_cu','VALIDATED_BY','exp_aalto_cu_2015'); E('find_L_au_cu','VALIDATED_BY','exp_aalto_cu_2016'); E('find_L_au_cu','DESCRIBED_IN','pub_b1');
E('find_L_pgm_cu','VALIDATED_BY','exp_aalto_cu_2016'); E('find_L_pgm_cu','DESCRIBED_IN','pub_b1');
E('find_L_ag_scatter','VALIDATED_BY','exp_roghani_2000'); E('find_L_ag_scatter','CONTRADICTS','find_L_au_cu'); E('find_L_ag_scatter','DESCRIBED_IN','pub_b1');
E('find_L_au_pt_pd_ni','VALIDATED_BY','exp_piskunen_2018'); E('find_L_au_pt_pd_ni','DESCRIBED_IN','pub_b1');
E('find_L_au_cu','OPERATES_AT_CONDITION','cond_matte_grade_65'); E('find_L_au_cu','OPERATES_AT_CONDITION','cond_temp_cu_equilibrium');
E('find_L_au_pt_pd_ni','OPERATES_AT_CONDITION','cond_temp_ni_equilibrium');
for(const m of ['mat_au','mat_ag','mat_pt','mat_pd','mat_rh']){ E('proc_matte_slag_equilibrium','HAS_PROPERTY',m); }

// ══════════════════════════════════════════════════════════════════════════
// КЛАСТЕР C — Кучное выщелачивание в холодном климате (пример из кейса!)
// ══════════════════════════════════════════════════════════════════════════
N('pub_c1','Технология кучного выщелачивания в условиях холодного климата (ТИ-05-2017)','Publication',{name:'Технология кучного выщелачивания и её применимость в условиях холодного климата', code:'ТИ – 05 – 2017', date:'2017', author:'С.В. Подоханова', geography:'RU+world', confidence:'подтверждено', source:'Обзоры/ТИ-5-2017. Кучное выщелачивание в условиях холодного климата.pdf'});
E('pub_c1','AUTHORED_BY','exp_podokhanova');

N('mat_ore_oxidized_cu','Окисленная медная руда','Material',{name:'Окисленная медная руда', kind:'Сырьё', composition:'малахит, азурит; ~0,4% Cu типично', confidence:'подтверждено', geography:'world', source:'pub_c1'});
N('mat_h2so4_leach','Серная кислота (для выщелачивания)','Material',{name:'Серная кислота', kind:'Реагент выщелачивания', dose:'расход 66–130 кг/т руды', confidence:'подтверждено', geography:'world', source:'pub_c1'});
N('mat_cu_cathode','Катодная медь','Material',{name:'Катодная медь (SX/EW)', kind:'Товарная продукция', purity:'высокая чистота, листы', confidence:'подтверждено', geography:'world', source:'pub_c1'});

N('proc_heap_leach','Кучное выщелачивание (КВ)','Process',{name:'Кучное выщелачивание окисленных медных руд', definition:'Дробление → окомкование с H2SO4 → укладка в штабель → орошение раствором H2SO4 → экстракция Cu → реэкстракция → электролиз (SX/EW)', confidence:'подтверждено', geography:'RU+world', source:'pub_c1'});
N('proc_agglomeration','Окомкование руды','Process',{name:'Окомкование (агломерация)', definition:'Добавка H2SO4 (15 кг/т) в барабанном окомкователе повышает прочность окатышей и сокращает продолжительность КВ', confidence:'подтверждено', geography:'RU+world', source:'pub_c1'});
N('proc_sxew','Экстракция–электролиз (SX/EW)','Process',{name:'SX/EW', definition:'Жидкостная экстракция меди из продуктивного раствора (LIX 984N/ShellSol D90), реэкстракция, электролиз медных катодов', confidence:'подтверждено', geography:'world', source:'pub_c1'});
E('proc_heap_leach','USES_MATERIAL','mat_ore_oxidized_cu'); E('proc_heap_leach','USES_MATERIAL','mat_h2so4_leach');
E('proc_heap_leach','PRODUCES_OUTPUT','mat_cu_cathode'); E('proc_heap_leach','PART_OF','proc_sxew'); E('proc_agglomeration','PART_OF','proc_heap_leach');

N('cond_cold_climate','Холодный климат (< -18°C средний зимний месяц)','Condition',{name:'Холодный климат', context:'Средняя t холодного месяца на изученных объектах от -6 до -31°C, продолжительность холодного периода 4–10 мес/год', confidence:'подтверждено', geography:'RU+world', source:'pub_c1'});
N('cond_heap_height','Высота штабеля КВ','Condition',{name:'Высота штабеля', min:2, max:8, unit:'м', context:'для руд Южного Урала рекомендовано не более 4 м', confidence:'подтверждено', geography:'RU+world', source:'pub_c1'});
N('cond_irrigation_rate','Плотность потока выщелачивающего раствора','Condition',{name:'Плотность орошения', value:5, unit:'л/(ч·м2), не более', confidence:'подтверждено', geography:'RU', source:'pub_c1'});
N('cond_solution_heating','Подогрев растворов на экстракцию','Condition',{name:'Требуемая температура раствора на экстракцию', value:15, unit:'°C, не менее', context:'ожидаемое охлаждение через штабель 9–12°C в холодный период', confidence:'подтверждено', geography:'RU', source:'pub_c1'});

N('find_ru_heap_leach_gap','Гэп: сернокислотное КВ никелевых руд в холодном климате в РФ не реализовано','Finding',{statement:'В изученном корпусе нет ни одного проекта классического сернокислотного кучного выщелачивания никелевых руд в холодном климате: единственный никелевый пример (Talvivaara/Terrafame, Финляндия) использует биовыщелачивание сульфидной руды, а не кислотное КВ. Комбинация «холодный климат + кучное выщелачивание + никелевая руда» — белое пятно в изученной литературе.', confidence:'гипотеза', n_sources:1, geography:'RU+world', source:'pub_c1', is_gap:true});
N('find_cold_climate_measures','Технические меры для КВ в холодном климате','Finding',{statement:'Для реализации КВ в условиях отрицательных температур рекомендуются: подогрев выщелачивающих растворов, заглубление системы орошения, теплоизоляция магистральных и продуктивных трубопроводов; при добавлении H2SO4 до 15 и 35 г/л раствор нагревается на 2°C и 5,2°C соответственно (теплота разбавления).', confidence:'подтверждено', n_sources:1, geography:'RU', source:'pub_c1'});
E('find_ru_heap_leach_gap','DESCRIBED_IN','pub_c1'); E('find_cold_climate_measures','DESCRIBED_IN','pub_c1'); E('find_cold_climate_measures','VALIDATED_BY','proc_heap_leach');
E('proc_heap_leach','OPERATES_AT_CONDITION','cond_cold_climate'); E('proc_heap_leach','OPERATES_AT_CONDITION','cond_heap_height');
E('proc_heap_leach','OPERATES_AT_CONDITION','cond_irrigation_rate'); E('proc_heap_leach','OPERATES_AT_CONDITION','cond_solution_heating');

const coldClimateFacilities = [
 ['fac_fort_knox','Fort Knox, Аляска, США','золото','world', '-22°C, 30 млн т/г, извл. 65%'],
 ['fac_casino','Casino, Юкон, Канада','медь-золото','world', '-16°C, проект, 8,8 млн т/г'],
 ['fac_talvivaara','Talvivaara/Terrafame, Финляндия','никель (биовыщелачивание)','world', '-12°C, 0,24% Ni; авария 2012 — утечка сточных вод, банкротство Talvivaara Sotkamo'],
 ['fac_veladero','Veladero, Аргентина','золото','world', '4000 м над ур. моря, -14°C, 29,5 млн т/г'],
 ['fac_actogay','Актогайский ГОК, Казахстан','медь','world', '-14°C, 12 млн т/г, KAZ Minerals'],
 ['fac_erdmin','Erdmin, Монголия','медь','world', '-24°C, 3000 т/г катодной меди, эксперимент с 1997'],
 ['fac_voroncovskoe','Воронцовское, Свердловская обл., РФ','золото','RU', '-24°C, ОАО «Полиметалл»'],
 ['fac_neryungri','Нерюнгри (м-е Таборное), Якутия, РФ','золото','RU', '-31°C, Nordgold, сезонная работа'],
 ['fac_aprelkovo','Апрелково, Забайкалье, РФ','золото','RU', '-24°C, Nordgold, извл. 57–64%'],
 ['fac_savkino','Савкино, Забайкалье, РФ','золото','RU', '-24°C, цианидное КВ, круглогодично'],
];
for(const [id,label,metal,geo,note] of coldClimateFacilities){
  N(id,label,'Facility',{name:label, kind:'Рудник/КВ-площадка', metal, geography:geo, note, confidence:'подтверждено', source:'pub_c1'});
  E(id,'PART_OF','proc_heap_leach'); E(id,'OPERATES_AT_CONDITION','cond_cold_climate');
}
E('find_ru_heap_leach_gap','MENTIONS','fac_talvivaara');

// ══════════════════════════════════════════════════════════════════════════
// КЛАСТЕР D — Очистка/обессоливание шахтных и сточных вод (запрос 1 и 4)
// ══════════════════════════════════════════════════════════════════════════
N('pub_d1','Методы очистки шахтных вод (ОИП-02-2025)','Publication',{name:'Методы очистки шахтных вод', code:'ОИП – 02 – 2025', date:'2025', author:'А.К. Евграфова', geography:'RU+world', confidence:'подтверждено', source:'Обзоры/Методы очистки шахтных вод.docx'});
N('pub_d2','Опыт применения озона при очистке промышленных сточных вод (ОИП-07-2024)','Publication',{name:'Опыт применения озона при очистке промышленных сточных вод', code:'ОИП – 07 – 2024', date:'2024', author:'С.В. Подоханова', geography:'world', confidence:'подтверждено', source:'Обзоры/ТИ Озонирование промышленных стоков.docx'});
E('pub_d1','AUTHORED_BY','exp_evgrafova'); E('pub_d2','AUTHORED_BY','exp_podokhanova');

N('mat_mine_water','Шахтная (рудничная) вода / MIW','Material',{name:'Шахтная вода (Mining Influenced Water)', kind:'Сточная вода', composition:'Fe, Al, Cu, Zn, Cd, Pb, Ni, Co, Cr при pH -3,5…5; As, Sb, Mo, U при нейтральном pH', confidence:'подтверждено', geography:'RU+world', source:'pub_d1'});
N('mat_sulfate_ion','Сульфат-ион (SO4²⁻)','Material',{name:'Сульфаты', kind:'Загрязнитель воды', confidence:'подтверждено', geography:'RU+world', source:'pub_d1'});
N('mat_chloride_ion','Хлорид-ион (Cl⁻)','Material',{name:'Хлориды', kind:'Загрязнитель воды', confidence:'подтверждено', geography:'RU+world', source:'pub_d1'});
N('mat_gypsum_byproduct','Гипс (CaSO4·2H2O)','Material',{name:'Гипс', kind:'Побочный продукт нейтрализации', formula:'Ca(OH)2 + H2SO4 → CaSO4·2H2O', confidence:'подтверждено', geography:'RU+world', source:'pub_d1'});

const waterProcesses = [
 ['proc_lime_neutral','Известковая нейтрализация (традиционная)','Осаждение/нейтрализация', 'Перемешивание+аэрация+удаление тв.; низкая скорость осаждения, большой объём шлама; удаляет 1500–2500 мг/л сульфата'],
 ['proc_hds','Процесс со шламом высокой плотности (HDS)','Осаждение/нейтрализация', 'Коррекция pH → нейтрализация/аэрация → сепарация тв/ж с рециркуляцией шлама; плотность шлама в десятки раз выше традиционного, экономия ~38% на шламоотделителе'],
 ['proc_limestone_neutral','Нейтрализация известняком','Осаждение/нейтрализация', 'Впервые в HDS у Anglo Coal (2001), экономия ~55%; дешевле извести, но требует контроля «бронирования» частиц'],
 ['proc_limestone_lime','Нейтрализация известняк/известь (2-3 стадии)','Осаждение/нейтрализация', 'Стадия 1 — известняк (окисление Fe2+, нейтрализация), стадия 2 — известь (осаждение Mg/сульфата), стадия 3 — CaCO3 из CO2; эффективна как предочистка перед обессоливанием'],
 ['proc_savmin','Процесс SAVMIN™','Осаждение/нейтрализация', 'Удаление металлов и сульфатов из шахтной воды в условиях окружающей среды; вода может соответствовать стандарту питьевой (ЮАР)'],
 ['proc_ro','Обратный осмос','Мембранный процесс', 'Классический метод глубокого обессоливания; ограничение — солеотложение (гипс) на мембране'],
 ['proc_nf','Нанофильтрация','Мембранный процесс', 'Селективна к многовалентным ионам (SO4²⁻), пропускает частично одновалентные (Cl⁻, Na⁺)'],
 ['proc_hipro','Процесс HiPRO® (ОО с высоким извлечением)','Мембранный процесс', 'Обратный осмос с осаждением гипса между ступенями — повышает извлечение пермеата сверх обычного предела RO'],
 ['proc_ed','Электродиализ / реверсивный электродиализ','Мембранный процесс', 'Перенос ионов через ионообменные мембраны под действием эл. поля; устойчив к отложениям при реверсе полярности'],
 ['proc_ix_traditional','Традиционный ионный обмен','Ионообменная технология', 'Смолы селективно связывают ионы жёсткости/сульфата, регенерация кислотой/щёлочью'],
 ['proc_gyp_cix','Процесс GYP-CIX','Ионообменная технология', 'Ионообменное удаление сульфата с предварительным осаждением гипса для снижения нагрузки на смолу'],
 ['proc_knew','Процесс KNeW','Ионообменная технология', 'Комбинация ионного обмена и нанофильтрации для обессоливания шахтных вод'],
 ['proc_bio_sulfate','Биологическое восстановление сульфата','Биологический процесс', 'Сульфатредуцирующие бактерии превращают сульфат в сульфид, осаждаемый как металл-сульфид'],
 ['proc_biosure','Процесс BioSURE®','Биологический процесс', 'Биологическая очистка кислых шахтных вод с получением H2S для селективного осаждения металлов'],
 ['proc_vitasoft','Процесс VitaSOFT','Биологический процесс', 'Биологическое умягчение и удаление сульфата'],
 ['proc_evaporation','Технологии испарения (MSF/MED/мех.сжатие пара)','Технология испарения', 'Многостадийная флэш-дистилляция, дистилляция с множественным эффектом, механическое сжатие пара — энергоёмкие методы глубокого обессоливания'],
 ['proc_freezing','Технологии замораживания','Технология вымораживания', 'Разделение льда (пресная вода) и концентрированного рассола вымораживанием'],
 ['proc_ozonation','Озонирование сточных вод','Окислительный процесс', 'Эффективно против цианидов, фенолов, органики; на заводе Cadillac (GM) снизило цианид на 97,6%'],
];
for(const [id,label,kind,def] of waterProcesses){
  N(id,label,'Process',{name:label, kind, definition:def, confidence:'подтверждено', geography:(id.includes('ru')?'RU':'world'), source:'pub_d1'});
  E(id,'USES_MATERIAL','mat_mine_water');
}
E('proc_ozonation','DESCRIBED_IN','pub_d2');

N('cond_sulfate_target','Целевой сухой остаток ≤1000 мг/дм3','Condition',{name:'Требуемый сухой остаток', value:1000, unit:'мг/дм3, не более', context:'типовое требование для оборотной воды обогатительной фабрики', confidence:'предварительно', geography:'RU', source:'pub_d1'});
N('cond_sulfate_input','Исходная минерализация 200–300 мг/л по SO4/Cl/Ca/Mg/Na','Condition',{name:'Исходная концентрация ионов', min:200, max:300, unit:'мг/л', context:'сульфаты, хлориды, Ca, Mg, Na — типовой состав оборотной воды ГОКа', confidence:'предварительно', geography:'RU', source:'pub_d1'});
N('cond_sulfate_removal_lime','Удаление сульфата известью','Condition',{name:'Диапазон удаления сульфата (известь)', min:1500, max:2500, unit:'мг/л', confidence:'подтверждено', geography:'world', source:'pub_d1'});

N('find_water_treatment_selection','Выбор метода обессоливания зависит от целевого остатка и состава примесей','Finding',{statement:'Известковая/известняковая нейтрализация эффективно удаляет многовалентные ионы (Ca, Mg как гипс/эттрингит), но НЕ удаляет Na и Cl (одновалентные противоионы) — для глубокого обессоливания (сухой остаток ≤1000 мг/дм3 при наличии Na/Cl) требуется мембранная стадия (обратный осмос/нанофильтрация/электродиализ) или ионный обмен (GYP-CIX/KNeW) после предочистки известью/известняком.', confidence:'подтверждено', n_sources:1, geography:'RU+world', source:'pub_d1'});
N('find_ro_scaling','Ограничение обратного осмоса — солеотложение гипса на мембране','Finding',{statement:'Классический обратный осмос ограничен осаждением гипса (CaSO4) на мембране при высоком пересыщении по сульфату кальция; процесс HiPRO® обходит это ограничение, осаждая гипс между ступенями осмоса, что повышает извлечение пермеата.', confidence:'подтверждено', n_sources:1, geography:'world', source:'pub_d1'});
E('find_water_treatment_selection','DESCRIBED_IN','pub_d1'); E('find_water_treatment_selection','VALIDATED_BY','proc_lime_neutral'); E('find_water_treatment_selection','VALIDATED_BY','proc_ro');
E('find_ro_scaling','DESCRIBED_IN','pub_d1'); E('find_ro_scaling','VALIDATED_BY','proc_ro'); E('find_ro_scaling','VALIDATED_BY','proc_hipro');
E('proc_lime_neutral','OPERATES_AT_CONDITION','cond_sulfate_removal_lime');
E('proc_ro','OPERATES_AT_CONDITION','cond_sulfate_target'); E('proc_nf','OPERATES_AT_CONDITION','cond_sulfate_target'); E('proc_ed','OPERATES_AT_CONDITION','cond_sulfate_target');
E('proc_lime_neutral','PRODUCES_OUTPUT','mat_gypsum_byproduct');

const waterFacilities = [
 ['fac_vale_sudbury','Vale, Садбери, Канада','world', 'организация водного хозяйства, водный цикл ГОКа'],
 ['fac_nkomati','Рудник Nkomati, ЮАР','world', 'Watercare Mining, высокоскоростная сепарация тв/ж'],
 ['fac_raglan','Рудник Raglan, Канада','world', 'BQE Water (BioteQ), очистка шахтных вод'],
 ['fac_dexing','Рудник Dexing, Китай','world', 'BQE Water, медный рудник'],
 ['fac_polychem','«Полихим», Россия','RU', 'технологии очистки шахтных вод'],
 ['fac_argel','«Аргель», Россия','RU', 'технологии очистки шахтных вод'],
];
for(const [id,label,geo,note] of waterFacilities){
  N(id,label,'Facility',{name:label, kind:'Предприятие/поставщик технологии', geography:geo, note, confidence:'подтверждено', source:'pub_d1'});
}
E('fac_vale_sudbury','MENTIONS','proc_lime_neutral'); E('fac_nkomati','MENTIONS','proc_hds');
E('fac_raglan','MENTIONS','proc_bio_sulfate'); E('fac_dexing','MENTIONS','proc_bio_sulfate');
E('fac_polychem','MENTIONS','mat_mine_water'); E('fac_argel','MENTIONS','mat_mine_water');

// ══════════════════════════════════════════════════════════════════════════
// КЛАСТЕР E — SO2/сера, сульфаты Ni/Co, синтетический ангидрит, обеднение шлаков
// ══════════════════════════════════════════════════════════════════════════
N('pub_e1','Методы концентрирования SO2 с получением элементарной серы (ИС-1-2016)','Publication',{name:'Методы концентрирования SO2 с последующим получением элементарной серы', code:'ИС – 1 – 2016', date:'2016', author:'С.В. Подоханова', geography:'world', confidence:'подтверждено', source:'Обзоры/Справка. Методы конц-я SO2.pdf'});
N('pub_e2','Обзор технологий получения сульфатов никеля и кобальта (ОИП-01-2022)','Publication',{name:'Обзор существующих технологий получения сульфатов никеля и кобальта', code:'ОИП – 01 – 2022', date:'2022', author:'А.К. Евграфова', geography:'world', confidence:'подтверждено', source:'Обзоры/ОИП-01-2022 Обзор существующих технологий получения сульфатов никеля и кобальта.docx'});
N('pub_e3','Синтетический ангидрит. Области применения','Publication',{name:'Синтетический ангидрит. Области применения', date:'2022', author:'А.К. Евграфова, С.В. Подоханова', geography:'RU+world', confidence:'подтверждено', source:'Обзоры/Применение синтетического ангидрита.docx'});
N('pub_e4','Исследования по обеднению никелевых конвертерных шлаков (ОИП-07-2022)','Publication',{name:'Исследования по обеднению никелевых конвертерных шлаков', code:'ОИП-07-2022', date:'2022', author:'С.В. Подоханова, А.К. Евграфова', geography:'world', confidence:'подтверждено', source:'Обзоры/ОИП-07-2022 Исследования по обеднению никелевых конвертерных шлаков.docx'});
for(const p of ['pub_e1','pub_e3']) E(p,'AUTHORED_BY','exp_podokhanova');
for(const p of ['pub_e2','pub_e4']) E(p,'AUTHORED_BY','exp_evgrafova');

N('mat_so2_gas','Диоксид серы (SO2)','Material',{name:'SO2 (отходящий газ)', kind:'Технологический газ', confidence:'подтверждено', geography:'world', source:'pub_e1'});
N('mat_elemental_sulfur','Элементарная сера','Material',{name:'Элементарная сера', kind:'Товарный продукт', confidence:'подтверждено', geography:'world', source:'pub_e1'});
N('mat_ni_sulfate','Сульфат никеля (NiSO4·6H2O)','Material',{name:'Сульфат никеля батарейного сорта', kind:'Товарная химическая продукция', purity:'>99,95% основного в-ва, <5 мг/кг Na (батарейный сорт)', confidence:'подтверждено', geography:'world', source:'pub_e2'});
N('mat_co_sulfate','Сульфат кобальта','Material',{name:'Сульфат кобальта', kind:'Товарная химическая продукция', confidence:'подтверждено', geography:'world', source:'pub_e2'});
N('mat_synthetic_anhydrite','Синтетический ангидрит (техногенный)','Material',{name:'Синтетический ангидрит CaSO4', kind:'Побочный продукт (напр. пр-ва HF)', formula:'CaF2 + H2SO4 → 2HF + CaSO4', confidence:'подтверждено', geography:'world', source:'pub_e3'});
N('mat_ni_converter_slag','Никелевый конвертерный шлак','Material',{name:'Никелевый конвертерный шлак', kind:'Отвальный продукт', confidence:'подтверждено', geography:'world', source:'pub_e4'});

for(const [id,label,def] of [
 ['proc_labsorb','Процесс Labsorb (ELSORB)','Извлечение SO2 из дымовых газов буфером на основе Na2HPO4; регенерируемый, извлекает концентрат SO2 90+%'],
 ['proc_cansolv','Система очистки Cansolv','Регенерируемая аминная технология селективной абсорбции SO2 с получением товарных побочных продуктов'],
 ['proc_clausmaster','Процесс ClausMaster (MECS)','Неводная физическая абсорбция SO2, возврат концентрата в процесс Клауса для извлечения серы'],
]) N(id,label,'Process',{name:label, definition:def, kind:'Концентрирование SO2', confidence:'подтверждено', geography:'world', source:'pub_e1'});
E('proc_labsorb','USES_MATERIAL','mat_so2_gas'); E('proc_cansolv','USES_MATERIAL','mat_so2_gas'); E('proc_clausmaster','USES_MATERIAL','mat_so2_gas');
E('proc_labsorb','PRODUCES_OUTPUT','mat_elemental_sulfur'); E('proc_cansolv','PRODUCES_OUTPUT','mat_elemental_sulfur'); E('proc_clausmaster','PRODUCES_OUTPUT','mat_elemental_sulfur');
N('find_so2_no_metallurgy_examples','Технологии концентрирования SO2 применяются в нефтегазе — примеров в металлургии не выявлено','Finding',{statement:'Labsorb, Cansolv и ClausMaster широко применяются для десульфуризации в нефтегазовой отрасли; несмотря на заявленную разработчиками гибкость, ни одного примера промышленного применения именно в металлургии в открытых источниках не обнаружено.', confidence:'гипотеза', n_sources:1, geography:'world', source:'pub_e1', is_gap:true});
E('find_so2_no_metallurgy_examples','DESCRIBED_IN','pub_e1');

N('proc_ni_sulfate_mhp','Производство сульфата никеля из MHP','Process',{name:'Производство NiSO4 из смешанных гидроксидов (MHP)', definition:'Доля MHP как сырья для сульфата никеля вырастет с 24% (2020) до 42%+ (2030) по прогнозу Roskill; интегрированные производители (напр. Норникель — сырьё из РФ, Sumitomo — MHP с Филиппин) занимают нижние квартили кривой затрат', confidence:'подтверждено', geography:'world', source:'pub_e2'});
N('proc_ni_sulfate_class1','Производство сульфата никеля из никеля Класса I','Process',{name:'Производство NiSO4 из рафинированного никеля (Класс I)', definition:'Более дорогое сырьё (порошки, брикеты); неинтегрированные производители, верхняя квартиль кривой затрат', confidence:'подтверждено', geography:'world', source:'pub_e2'});
E('proc_ni_sulfate_mhp','PRODUCES_OUTPUT','mat_ni_sulfate'); E('proc_ni_sulfate_class1','PRODUCES_OUTPUT','mat_ni_sulfate');
N('cond_ni_price_2019','Средняя цена сульфата никеля 2019','Condition',{name:'Цена NiSO4', value:15521, unit:'USD/т Ni (2019)', confidence:'подтверждено', geography:'world', source:'pub_e2'});
E('proc_ni_sulfate_mhp','OPERATES_AT_CONDITION','cond_ni_price_2019');

N('proc_anhydrite_use_construction','Применение синтетического ангидрита в стройматериалах','Process',{name:'Ангидрит в наливных полах, штукатурках, цементе', definition:'За рубежом широко используется (компания Fluorsid, продукт Gypsos); в РФ распространено недостаточно, есть разработки НИТУ «МИСиС» (2021) по синтезу гипса/ангидрита из отходов химзаводов', confidence:'подтверждено', geography:'RU+world', source:'pub_e3'});
E('proc_anhydrite_use_construction','USES_MATERIAL','mat_synthetic_anhydrite');
N('find_anhydrite_ru_lag','РФ отстаёт от мировой практики применения синтетического ангидрита в стройиндустрии','Finding',{statement:'Производство стройматериалов из ангидритового сырья в России развито недостаточно, тогда как за рубежом (Fluorsid/Gypsos и др.) технология применяется широко в цементной промышленности, наливных полах и штукатурках. НИТУ «МИСиС» в 2021 г. разработал низкозатратный одностадийный метод синтеза при 45–55°C (вместо обжига при 800–1000°C).', confidence:'подтверждено', n_sources:1, geography:'RU+world', source:'pub_e3'});
E('find_anhydrite_ru_lag','DESCRIBED_IN','pub_e3'); E('find_anhydrite_ru_lag','VALIDATED_BY','proc_anhydrite_use_construction');

N('proc_slag_depletion_don','Обеднение шлаков DON (биочар/CH4)','Process',{name:'Обеднение конвертерных шлаков DON', definition:'Восстановление биочаром + батарейным скрапом или смесью CH4(5%)-N2', confidence:'предварительно', geography:'world', source:'pub_e4'});
N('proc_slag_depletion_gypsum','Обеднение Cu-Co шлака с гипсом как сульфидизатором','Process',{name:'Сульфидирование CaSO4/CaS при обеднении Cu-Co шлака', definition:'Гипс из отвалов рассматривается как перспективный сульфидирующий агент для обеднения кобальтсодержащих медных шлаков', confidence:'гипотеза', geography:'world', source:'pub_e4'});
N('eq_ausmelt','Печь Ausmelt','Equipment',{name:'Печь Ausmelt', kind:'Плавильный/обеднительный агрегат', confidence:'предварительно', geography:'world', source:'pub_e4'});
N('eq_dc_furnace','Обеднительная печь постоянного тока','Equipment',{name:'Печь постоянного тока (DC)', kind:'Обеднительный агрегат', confidence:'подтверждено', geography:'world', source:'pub_e4'});
N('eq_electric_furnace','Электропечь (обеднительная)','Equipment',{name:'Электропечь', kind:'Обеднительный агрегат', confidence:'подтверждено', geography:'world', source:'pub_e4'});
E('proc_slag_depletion_don','USES_MATERIAL','mat_ni_converter_slag'); E('proc_slag_depletion_gypsum','USES_MATERIAL','mat_ni_converter_slag'); E('proc_slag_depletion_gypsum','USES_MATERIAL','mat_synthetic_anhydrite');
E('proc_slag_depletion_gypsum','USES_EQUIPMENT','eq_dc_furnace'); E('proc_slag_depletion_don','USES_EQUIPMENT','eq_electric_furnace');
E('pub_e4','MENTIONS','eq_ausmelt'); E('pub_e4','MENTIONS','proc_slag_depletion_don'); E('pub_e4','MENTIONS','proc_slag_depletion_gypsum');
E('proc_slag_depletion_gypsum','CONTRADICTS','proc_anhydrite_use_construction');

// ══════════════════════════════════════════════════════════════════════════
// КЛАСТЕР F — Обжиг-выщелачивание, хлорное и цианидное выщелачивание
// ══════════════════════════════════════════════════════════════════════════
N('pub_f1','Переработка медно-никелевых штейнов: обжиг-выщелачивание (ОИП-09-2018)','Publication',{name:'Переработка медно-никелевых штейнов (обжиг-выщелачивание)', code:'ОИП – 09 – 2018', date:'2018', author:'А.К. Евграфова, С.В. Подоханова', geography:'world', confidence:'подтверждено', source:'Обзоры/Обзор пеработка медно-никелевых штейнов (обжиг-выщелачивание) фул.docx'});
N('pub_f2','Технологии хлорного выщелачивания никеля (ОИП-02-2024)','Publication',{name:'Технологии хлорного выщелачивания никеля', code:'ОИП – 02 – 2024', date:'2024', author:'А.К. Евграфова', geography:'world', confidence:'подтверждено', source:'Обзоры/Хлорное выщелачивание ОИП 02-2024.docx'});
N('pub_f3','Цианидное выщелачивание МПГ (ОИП-11-2020)','Publication',{name:'Цианидное выщелачивание МПГ', code:'ОИП – 11 – 2020', date:'2020', author:'А.К. Евграфова', geography:'world', confidence:'подтверждено', source:'Обзоры/Цианидное выщелачивание МПГ.docx'});
for(const p of ['pub_f1','pub_f2','pub_f3']) E(p,'AUTHORED_BY','exp_evgrafova');

N('mat_finestein','Файнштейн (Cu-Ni)','Material',{name:'Файнштейн', kind:'Промпродукт конвертирования', composition:'Ni~48%, Cu~27%, S~22% (канадский, типично)', confidence:'подтверждено', geography:'world', source:'pub_f1'});
N('proc_hybinette','Процесс Хибинетта','Process',{name:'Процесс Хибинетта (Hybinette)', definition:'Обжиг файнштейна при ~800°C в многоподовых печах Герресхофа → выщелачивание H2SO4 (отработанным электролитом) → анодная плавка остатка Ni → электролиз; применялся на Nikkelverk до 1978 г.', confidence:'подтверждено', geography:'world', source:'pub_f1'});
N('eq_herreshoff','Многоподовая печь Герресхофа','Equipment',{name:'Печь Герресхофа (Herreshoff)', kind:'Обжиговый агрегат', confidence:'подтверждено', geography:'world', source:'pub_f1'});
E('proc_hybinette','USES_MATERIAL','mat_finestein'); E('proc_hybinette','USES_EQUIPMENT','eq_herreshoff'); E('proc_hybinette','PART_OF','proc_ew_so4');
E('fac_nikkelverk','PART_OF','proc_hybinette');

N('proc_chloride_leach_ni','Хлорное выщелачивание файнштейна','Process',{name:'Хлорное выщелачивание никелевого файнштейна', definition:'Более 30 лет применяется на Nikkelverk (CLP), Niihama и Sandouville; двухстадийная схема также на Long Harbour (Канада) для сульфидных концентратов Voisey\'s Bay', confidence:'подтверждено', geography:'world', source:'pub_f2'});
E('proc_chloride_leach_ni','USES_MATERIAL','mat_finestein'); E('proc_chloride_leach_ni','PART_OF','proc_ew_cl');
N('fac_long_harbour','Long Harbour, Канада','Facility',{name:'Long Harbour', kind:'Никелерафинировочный завод', owner:'Vale', geography:'world', note:'двухстадийное выщелачивание сульфидных концентратов Voisey\'s Bay', confidence:'подтверждено', source:'pub_f2'});
E('fac_long_harbour','PART_OF','proc_chloride_leach_ni'); E('fac_nikkelverk','PART_OF','proc_chloride_leach_ni'); E('fac_niihama','PART_OF','proc_chloride_leach_ni'); E('fac_sandouville','PART_OF','proc_chloride_leach_ni');

N('mat_pgm_concentrate','МПГ-содержащий флотоконцентрат','Material',{name:'Флотационный концентрат с МПГ', kind:'Промпродукт обогащения', confidence:'подтверждено', geography:'world', source:'pub_f3'});
N('proc_cyanide_leach_pgm','Цианидное выщелачивание МПГ','Process',{name:'Цианидное выщелачивание МПГ', definition:'Проект Panton (Австралия, Platinum Australia/Lonmin): обжиг концентрата (400–425°C, 1ч) → цианидное выщелачивание (t 60°C, CN 0,2%вес, pH 9,2, 100ч) → извлечение Pd 86%, Au 99%, Pt <10%', confidence:'предварительно', geography:'world', source:'pub_f3'});
E('proc_cyanide_leach_pgm','USES_MATERIAL','mat_pgm_concentrate');
N('cond_panton_conditions','Условия цианидного выщелачивания Panton','Condition',{name:'t=60°C, CN 0,2%вес, pH 9,2, 100ч', context:'проект Panton, Западная Австралия', confidence:'предварительно', geography:'world', source:'pub_f3'});
E('proc_cyanide_leach_pgm','OPERATES_AT_CONDITION','cond_panton_conditions');
N('find_cyanide_pt_low','Цианидное выщелачивание слабо извлекает платину','Finding',{statement:'При атмосферном цианидном выщелачивании обожжённого МПГ-концентрата (проект Panton) извлечение палладия достигло 86% и золота 99%, но платины — менее 10%; измельчение до Р80 14 мкм дало лишь незначительный эффект. Технология Platsol дала до 95% извлечения МПГ, но с неприемлемо высоким расходом реагентов.', confidence:'предварительно', n_sources:1, geography:'world', source:'pub_f3'});
E('find_cyanide_pt_low','DESCRIBED_IN','pub_f3'); E('find_cyanide_pt_low','VALIDATED_BY','proc_cyanide_leach_pgm');
E('find_cyanide_pt_low','CONTRADICTS','find_L_pgm_cu');

// ── Общая связка: практики РФ vs мировая по обессоливанию (для сравнительных запросов) ──
E('proc_hds','APPLIES_TO','cond_sulfate_input'); E('proc_gyp_cix','APPLIES_TO','cond_sulfate_input'); E('proc_ro','APPLIES_TO','cond_sulfate_input');

// Публикации-упоминания дополнительных материалов из корпуса (для широты покрытия и "институциональной памяти")
const extraPublications = [
 ['pub_extra1','ОИП-05-2019 Параметры Cu EW','2019','Параметры электроэкстракции меди'],
 ['pub_extra2','ИС-4-2017 Краткий обзор медно-никелевых обогатительных фабрик','2017','Обзор обогатительных фабрик'],
 ['pub_extra3','Обзор технологий переработки Cu-Ni шлаков (2024)','2024','Переработка шлаков'],
 ['pub_extra4','ОИП-04-2019 Новые рудники бедной сульфидной Cu-Ni руды','2019','Рудники Cu-Ni'],
];
for(const [id,label,date,kind] of extraPublications){
  N(id,label,'Publication',{name:label, date, kind, geography:'world', confidence:'предварительно', source:'Обзоры/'+label+'.docx (заголовок из каталога, не разобран детально)'});
  E(id,'AUTHORED_BY','exp_evgrafova');
}
E('pub_extra1','MENTIONS','proc_ew_so4'); E('pub_extra2','MENTIONS','mat_ore_oxidized_cu'); E('pub_extra3','MENTIONS','mat_ni_converter_slag'); E('pub_extra4','MENTIONS','mat_cu_matte');
