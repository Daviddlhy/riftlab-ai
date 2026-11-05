{% macro generate_schema_name(custom_schema_name, node) -%}
    {# La base de la cible sépare les environnements. Garder les noms de schéma exacts. #}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
