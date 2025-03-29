import geopandas as gpd
import osmnx as ox
import pandas as pd
from typing import Optional
import numpy as np
from shapely.geometry import box
import math


def extract_landuse_within_polygon(input_polygon):
    """
    Выгружает объекты landuse из заданного полигона.
    """
    boundary = input_polygon.geometry.iloc[0]
    if boundary.is_empty or not boundary.is_valid:
        print("Ошибка: граница пустая или невалидная.")
        return gpd.GeoDataFrame(columns=['geometry'])

    tags = {
        'landuse': [
            'residential', 'apartments', 'detached', 'construction', 'allotments',
            'industrial', 'quarry', 'landfill', 'cemetery', 'military', 'railway',
            'brownfield', 'national_park', 'protected_area', 'nature_reserve',
            'conservation', 'farmland', 'farmyard', 'orchard', 'vineyard',
            'greenhouse_horticulture', 'meadow', 'plant_nursery', 'aquaculture',
            'animal_keeping', 'breeding', 'port', 'depot', 'commercial',
            'fairground', 'retail', 'grass', 'greenfield', 'forest', 'garages'
        ],
        'natural': ['forest', 'wood', 'wetland', 'scrub', 'heath', 'scree', 'grass', 'grassland'],
        'leisure': ['park', 'dog_park', 'garden'],
        'aeroway': ['heliport', 'aerodrome'],
        'place': ['neighbourhood'],
        'amenity': ['school', 'kindergarten'],
        'tourism': ['museum']
    }

    all_landuse_data = []

    for key, values in tags.items():
        try:
            landuse_data = ox.features_from_polygon(boundary, tags={key: values})
            if not landuse_data.empty:
                landuse_data['geometry'] = landuse_data['geometry'].apply(lambda geom: geom.buffer(0) if not geom.is_valid else geom)
                landuse_data = landuse_data[landuse_data.geometry.is_valid]
                landuse_data = landuse_data.clip(boundary)
                landuse_data = landuse_data[~landuse_data.geometry.is_empty]
                all_landuse_data.append(landuse_data)
            else:
                print(f"Предупреждение: для ключа '{key}' не найдено объектов.")
        except Exception as e:
            print(f"Не удалось найти объекты для ключа '{key}': {e}")

    if all_landuse_data:
        return gpd.GeoDataFrame(pd.concat(all_landuse_data, ignore_index=True))
    else:
        print("Результирующий GeoDataFrame пуст.")
        return gpd.GeoDataFrame(columns=['geometry'])


def assign_landuse_zone(row):
    landuse_mapping = {
        'industrial': 'Industrial',
        'quarry': 'Industrial',
        'residential': 'Residential',
        'apartments': 'Residential',
        'detached': 'Residential',
        'construction': 'Residential',
        'allotments': 'Residential',
        'military': 'Special',
        'railway': 'Transport',
        'cemetery': 'Special',
        'landfill': 'Special',
        'brownfield': 'Special',
        'port': 'Transport',
        'depot': 'Transport',
        'national_park': 'Recreation',
        'protected_area': 'Recreation',
        'nature_reserve': 'Recreation',
        'conservation': 'Recreation',
        'grass': 'Recreation',
        'greenfield': 'Recreation',
        'forest': 'Recreation',
        'farmland': 'Agriculture',
        'farmyard': 'Agriculture',
        'orchard': 'Agriculture',
        'vineyard': 'Agriculture',
        'greenhouse_horticulture': 'Agriculture',
        'meadow': 'Agriculture',
        'plant_nursery': 'Agriculture',
        'aquaculture': 'Agriculture',
        'animal_keeping': 'Agriculture',
        'breeding': 'Agriculture',
        'commercial': 'Business',
        'fairground': 'Business',
        'retail': 'Business',
        'garages': 'Residential'
    }

    landuse_zone = landuse_mapping.get(row['landuse'])

    if landuse_zone is None:
        if row.get('natural') in ['forest', 'wood', 'wetland', 'scrub', 'heath', 'scree', 'grass', 'grassland']:
            return 'Recreation'
        if row.get('leisure') in ['park', 'dog_park', 'garden']:
            return 'Recreation'
        if row.get('aeroway') in ['heliport', 'aerodrome']:
            return 'Special'
        if row.get('place') in ['neighbourhood']:
            return 'Residential'
        if row.get('amenity') in ['school', 'kindergarten']:
            return 'Residential'
        if row.get('tourism') in ['museum']:
            return 'Special'

    return landuse_zone


def loading_water_OSM(boundary_gdf):
    try:
        osm_objects = ox.features_from_polygon(boundary_gdf.geometry.unary_union,
                                                 tags={'natural': ['basin', 'reservoir', 'water', 'salt_pond', 'bay']})
    except Exception as e:
        print(f"Ошибка при загрузке данных из OSM тип 1: {e}")
        osm_objects = gpd.GeoDataFrame()

    return osm_objects


def subtract_polygons(landuse_gdf):
    # Фильтруем невалидные геометрии
    landuse_gdf = landuse_gdf[landuse_gdf.geometry.is_valid]

    result_polygons = []
    result_attributes = {
        'landuse': [],
        'natural': [],
        'landuse_zon': [],
        'leisure': [],
        'aeroway': [],
        'place': [],
        'amenity': [],
        'tourism': [],
    }

    for i, poly in landuse_gdf.iterrows():
        current_polygon = poly.geometry

        if current_polygon.geom_type not in ['Polygon', 'MultiPolygon']:
            continue

        # Исправление невалидных геометрий
        if not current_polygon.is_valid:
            current_polygon = current_polygon.buffer(0)  # Попытка исправления

            if not current_polygon.is_valid:
                print(f"Невалидный полигон на индексе {i} после исправления: {current_polygon}")
                continue  # Пропускаем, если геометрия всё ещё невалидна

        attributes = {key: poly.get(key, None) for key in result_attributes.keys()}

        # Вычисление пересечений
        overlaps = []
        for other_poly in result_polygons:
            try:
                if current_polygon.intersects(other_poly):
                    overlaps.append(other_poly)
            except Exception:
                print(f"Couldn't process poly with id == {i}")
                continue

        for overlap in overlaps:
            # Исправляем геометрии перед вычитанием
            current_polygon = current_polygon.make_valid() if hasattr(current_polygon,
                                                                      'make_valid') else current_polygon
            overlap = overlap.make_valid() if hasattr(overlap, 'make_valid') else overlap

            # Вычитаем пересекающиеся полигоны
            current_polygon = current_polygon.difference(overlap)

        # Добавляем только валидные и не пустые полигоны
        if not current_polygon.is_empty and current_polygon.is_valid:
            result_polygons.append(current_polygon)
            for key in result_attributes.keys():
                result_attributes[key].append(attributes[key])

    # Создание нового GeoDataFrame
    result_gdf = gpd.GeoDataFrame(geometry=gpd.GeoSeries(result_polygons))

    # Добавление атрибутов
    for key in result_attributes.keys():
        result_gdf[key] = result_attributes[key] if result_attributes[key] else [None] * len(result_gdf)

    # Фильтр по валидным геометриям
    result_gdf = result_gdf[result_gdf.geometry.is_valid]

    return result_gdf


def analyze_and_process_landuse_data(landuse_data):
    """
    Производит операции с выгруженными данными landuse.
    """
    landuse_data = extract_landuse_within_polygon(landuse_data)
    if landuse_data.empty:
        return gpd.GeoDataFrame(columns=['geometry'])

    landuse_data['landuse_zon'] = landuse_data.apply(assign_landuse_zone, axis=1)
    result_gdf = subtract_polygons(landuse_data)

    return result_gdf

def classify_urbanization_levels(geo_dataframe):
    geo_dataframe.loc[geo_dataframe['natural'].notnull() & (geo_dataframe['landuse_zon'] == 'Recreation'), 'Процент урбанизации'] = 'Мало урбанизированная территория'
    geo_dataframe.loc[geo_dataframe['natural'].isnull() & (geo_dataframe['landuse_zon'] == 'Recreation'), 'Процент урбанизации'] = 'Высоко урбанизированная территория'
    geo_dataframe.loc[geo_dataframe['natural'] == 'grassland', 'Процент урбанизации'] = 'Высоко урбанизированная территория'
    geo_dataframe.loc[geo_dataframe['landuse'] == 'farmland', 'Процент урбанизации'] = 'Хорошо урбанизированная территория'
    geo_dataframe.loc[geo_dataframe['landuse'] == 'meadow', 'Процент урбанизации'] = 'Мало урбанизированная территория'
    geo_dataframe.loc[geo_dataframe['landuse'] == 'cemetery', 'Процент урбанизации'] = 'Высоко урбанизированная территория'
    geo_dataframe.loc[geo_dataframe['tourism'] == 'museum', 'Процент урбанизации'] = 'Высоко урбанизированная территория'

    return geo_dataframe


def calculate_building_percentages(df):
    # Фильтруем только те строки, где is_living равно 1 и есть значение в building:levels
    df_buildings = df[(df['is_living'] == 1) & (df['building:levels'].notna())]

    total_buildings = len(df_buildings)

    # Подсчет зданий в каждой категории
    building_counts = {
        'ИЖС': df_buildings['building:levels'].isin([1, 2]).sum(),
        'Малоэтажная': df_buildings['building:levels'].between(3, 4).sum(),
        'Среднеэтажная': df_buildings['building:levels'].between(5, 8).sum(),
        'Многоэтажная': (df_buildings['building:levels'] > 8).sum()
    }

    # Вычисление процентов
    percentages = {key: (count / total_buildings * 100 if total_buildings > 0 else 0)
                   for key, count in building_counts.items()}

    return pd.Series(percentages)


def calculate_area_percentage(buildings_in_zone, zone):
    zone_area = zone.geometry.area if hasattr(zone, 'geometry') else 0

    total_building_area = 0
    total_living_area = 0  # Переменная для площади жилых зданий

    # Проходим по каждому зданию в buildings_in_zone
    for _, building in buildings_in_zone.iterrows():
        if building['is_living'] in [0, 1]:  # Проверяем значение is_living
            building_area = building.geometry.area
            total_building_area += building_area

            # Если зона жилая, суммируем только жилые здания
            if zone.get('landuse_zon') == 'Residential' and building['is_living'] == 1:
                total_living_area += building_area

    # Рассчитываем процент площади зданий к площади зоны
    area_percentage = (total_building_area / zone_area * 100) if zone_area > 0 else 0

    # Рассчитываем процент площади жилых зданий к площади зоны
    living_area_percentage = (total_living_area / zone_area * 100) if zone.get(
        'landuse_zon') == 'Residential' and zone_area > 0 else 0

    return area_percentage, living_area_percentage


def assign_development_type(gdf):
    gdf['Застройка'] = None
    gdf['Процент урбанизации'] = None

    # Преобразуем значения в числовые и находим тип застройки с максимальным значением
    development_types = ['ИЖС', 'Малоэтажная', 'Среднеэтажная', 'Многоэтажная']
    values = gdf[development_types].apply(pd.to_numeric, errors='coerce')
    gdf['Застройка'] = values.idxmax(axis=1).where(values.max(axis=1) > 0)

    # Определяем процент урбанизации в зависимости от значения 'Любые дома /на зону'
    conditions = [
        (gdf['Любые дома /на зону'].isna()) | (gdf['Любые дома /на зону'] == 0),
        (gdf['Любые дома /на зону'] < 10),
        (gdf['Любые дома /на зону'] < 25),
        (gdf['Любые дома /на зону'] < 75),
        (gdf['Любые дома /на зону'] < 90),
        (gdf['Любые дома /на зону'] >= 90)
    ]

    choices = [
        'Мало урбанизированная территория',
        'Мало урбанизированная территория',
        'Слабо урбанизированная территория',
        'Средне урбанизированная территория',
        'Хорошо урбанизированная территория',
        'Высоко урбанизированная территория'
    ]

    gdf['Процент урбанизации'] = np.select(conditions, choices, default=None)

    return gdf


def is_living_building(row: gpd.GeoSeries):
    return 1 if row["building"] in ("apartments", "house", "residential", "detached", "dormitory", "semidetached_house") else 0


def calculate_living_area(source: gpd.GeoDataFrame):
    df = source.copy()
    df['area'] = df.to_crs(3857).geometry.area.astype(float)

    if 'building:levels' not in df.columns:
        raise ValueError("Файл GeoDataFrame не содержит столбец 'building:levels'")

    if not df.empty:
        # Обработка значений в столбце 'building:levels'
        df['building:levels'] = df['building:levels'].fillna('1')  # Заполнение NaN значением '1'

        def safe_convert(levels):
            try:
                if ';' in levels:
                    return max(math.ceil(float(x)) for x in levels.split(';'))
                return math.ceil(float(levels))
            except ValueError:
                print(f"Ошибка преобразования уровня: {levels}. Округляем в большую сторону.")
                return 1  # Значение по умолчанию в случае ошибки

        df['building:levels'] = df['building:levels'].apply(safe_convert)

        return df
    else:
        raise ValueError("GeoDataFrame пустой.")

def split_polygon_grid(polygon, num_parts):

    minx, miny, maxx, maxy = polygon.bounds

    width = (maxx - minx) / num_parts
    height = (maxy - miny) / num_parts

    grid = []
    for i in range(num_parts):
        for j in range(num_parts):
            grid.append(box(minx + i * width, miny + j * height,
                            minx + (i + 1) * width, miny + (j + 1) * height))

    return gpd.GeoDataFrame(geometry=grid).clip(polygon)

def refine_boundary_with_osm_data(boundary_gdf, objects_gdf):
    osm_objects = loading_water_OSM(boundary_gdf)

    boundary_polygon = boundary_gdf.geometry.unary_union

    result_polygon = boundary_polygon.difference(
        osm_objects.geometry.unary_union) if not osm_objects.empty else boundary_polygon
    remaining_polygon = result_polygon.difference(objects_gdf.geometry.unary_union)

    if remaining_polygon.is_empty:
        print("Оставшийся полигон пуст, ничего не будет объединено.")
        return objects_gdf, gpd.GeoDataFrame()

    num_parts = 25
    smaller_gdf = split_polygon_grid(remaining_polygon, num_parts)

    updated_objects_gdf = pd.concat([objects_gdf, smaller_gdf], ignore_index=True)

    return updated_objects_gdf


def extract_and_analyze_buildings_within_polygon(polygon) -> Optional[gpd.GeoDataFrame]:
    if polygon is None:
        return None
    # Загружаем здания из полигона
    buildings = ox.features_from_polygon(polygon.geometry.unary_union, tags={"building": True})
    print("Здания загружены.")

    # Фильтруем только полигоны и многоугольники
    buildings = buildings[buildings['geometry'].geom_type.isin(['Polygon', 'MultiPolygon'])].copy()
    print('Здания отфильтрованы.')

    # Определяем жилые здания и вычисляем их площадь
    buildings["is_living"] = buildings.apply(is_living_building, axis=1)
    buildings = calculate_living_area(buildings)
    print("Площадь вычислена.")
    # Загружаем полигоны зон
    landuse_polygons = analyze_and_process_landuse_data(polygon)

    print("Полигоны зон загружены.")
    # Фильтруем здания внутри зонo

    if landuse_polygons.crs is None:
        landuse_polygons = landuse_polygons.set_crs(4326)
    print('Нарезка полигонов готова.')

    buildings_within_landuse = buildings[
        buildings.to_crs(3857).geometry.within(landuse_polygons.to_crs(3857).unary_all)]
    landuse_polygons = refine_boundary_with_osm_data(polygon, landuse_polygons)
    landuse_polygons[['ИЖС', 'Малоэтажная', 'Среднеэтажная', 'Многоэтажная']] = 0.0
    local_crs = buildings_within_landuse.estimate_utm_crs()

    buildings_within_landuse.to_crs(local_crs, inplace=True)
    landuse_polygons.to_crs(local_crs, inplace=True)

    for idx, zone in landuse_polygons.iterrows():
        buildings_in_zone = buildings_within_landuse[buildings_within_landuse.geometry.within(zone.geometry)]

        percentages = calculate_building_percentages(buildings_in_zone)

        landuse_polygons.loc[idx, ['ИЖС', 'Малоэтажная', 'Среднеэтажная', 'Многоэтажная']] = percentages

        area_percentage, living_area_percentage = calculate_area_percentage(buildings_in_zone, zone)
        landuse_polygons.at[idx, 'Любые дома /на зону'] = area_percentage
        landuse_polygons.at[idx, 'Только жилые дома /на зону'] = living_area_percentage

    # Применяем функции для определения типа застройки и процентов
    landuse_polygons = assign_development_type(landuse_polygons)
    print('Тип застройки присвоен.')
    landuse_polygons = classify_urbanization_levels(landuse_polygons)
    print('Классификация выполнена.')

    # Формируем результат
    result = landuse_polygons[['landuse', 'natural', 'leisure', 'tourism', 'aeroway', 'amenity', 'ИЖС',
                               'Малоэтажная', 'Среднеэтажная', 'Многоэтажная', 'geometry',
                               'landuse_zon', 'Любые дома /на зону', 'Только жилые дома /на зону',
                               'Застройка', 'Процент урбанизации']]
    buildings_within_landuse = buildings_within_landuse[['geometry', 'is_living', 'building:levels']]

    return result


def analyze_geojson_for_renovation_potential(file_path, excluded_zone):
    geo_data = extract_and_analyze_buildings_within_polygon(file_path)

    geo_data['Площадь'] = geo_data.geometry.area

    # Инициализация нового столбца "Потенциал" со значением "Подлежащие реновации"
    geo_data['Потенциал'] = 'Подлежащие реновации'

    # Условия для исключений
    conditions = [
        (geo_data['landuse_zon'] == 'Residential') & (geo_data['amenity'].notna()),
        (geo_data['landuse_zon'] == 'Recreation') & (
                    geo_data['Процент урбанизации'] == 'Высоко урбанизированная территория'),
        (geo_data['landuse_zon'] == 'Special') & (geo_data['aeroway'].notna()),
        (geo_data['landuse_zon'] == 'Special') & (geo_data['tourism'].notna()),
        (geo_data['landuse_zon'] == 'Special') & (geo_data['landuse'] == 'cemetery'),
        (geo_data['landuse_zon'] == 'Residential') & (geo_data['Многоэтажная'] > 50)
    ]

    # Добавление условия для исключенной зоны
    if excluded_zone in geo_data['landuse_zon'].unique():
        conditions.append(geo_data['landuse_zon'] == excluded_zone)

    for condition in conditions:
        geo_data.loc[condition, 'Потенциал'] = None

        # Расчет площади подлежащей реновации
    total_area = geo_data['Площадь'].sum()
    renovation_area = geo_data[geo_data['Потенциал'].isnull()]['Площадь'].sum()

    # Рассчитываем коэффициент "неудобия"
    discomfort_coefficient = (renovation_area / total_area * 100) if total_area > 0 else 0

    geo_data['Неудобия'] = discomfort_coefficient

    geo_data = geo_data[geo_data['Площадь'] > 0]
    geo_data = geo_data.to_crs(epsg=4326)

    return geo_data

geojson_file_path = 'Test.geojson'
geojson_file_path = gpd.read_file(geojson_file_path)
combined_data = analyze_geojson_for_renovation_potential(geojson_file_path,'Residential')
combined_data.to_file('Test 2.geojson')

