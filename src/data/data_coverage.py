"""Whole-universe coverage without carrying a selected stock or sector filter."""

def project_coverage(product):
    if product.get('group') != 'all':
        raise ValueError('Độ phủ phải tính cho toàn bộ ngành trong phạm vi.')
    data = product['data_status']
    return {
        'schema_version': 1, 'mode': 'data_coverage', 'source': product['source'],
        'universe': product['universe'], 'group': 'all',
        'available_universes': product['available_universes'],
        'updated_at': product['updated_at'], 'coverage': product['coverage'],
        'analysis': {key: product['analysis'].get(key) for key in ('mode', 'label', 'asof')},
        'invalid_symbols': [row['symbol'] for row in product['ranking'] if not row['valid']],
        'data_status': {key: value for key, value in data.items()
                        if key not in ('price_time', 'book_time', 'price_basis')},
    }
