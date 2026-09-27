REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO wh_viewer, wh_analyst;

REVOKE ALL ON ALL TABLES IN SCHEMA public FROM wh_viewer, wh_analyst;

GRANT SELECT ON regions, stores, categories, products, inventory, promotions,
                orders, order_items, payments, returns
      TO wh_viewer;
GRANT SELECT ON v_customers_masked, v_employees_masked TO wh_viewer;

GRANT SELECT ON ALL TABLES IN SCHEMA public TO wh_analyst;

-- Defense in depth: roles can SET session options, so shut the side doors a
-- single SELECT could use (set_config, sleeps) and forbid temp-table writes.
DO $$ BEGIN
    EXECUTE format('REVOKE TEMPORARY ON DATABASE %I FROM PUBLIC', current_database());
END $$;
