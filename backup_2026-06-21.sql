--
-- PostgreSQL database dump
--

\restrict wY77mSb5ix07ymW5CbnhdEvUYBERxgmrtgHmdp9LdShOxn4OMBW8EmnY38j8mjP

-- Dumped from database version 16.14 (Debian 16.14-1.pgdg13+1)
-- Dumped by pg_dump version 16.14 (Debian 16.14-1.pgdg13+1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: set_updated_at(); Type: FUNCTION; Schema: public; Owner: admin
--

CREATE FUNCTION public.set_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;


ALTER FUNCTION public.set_updated_at() OWNER TO admin;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: asset_pools; Type: TABLE; Schema: public; Owner: admin
--

CREATE TABLE public.asset_pools (
    id bigint NOT NULL,
    code character varying(32) NOT NULL,
    name character varying(200) NOT NULL,
    status character varying(32) DEFAULT 'pending'::character varying NOT NULL,
    appraised_value numeric(18,2) DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT chk_asset_pools_value CHECK ((appraised_value >= (0)::numeric))
);


ALTER TABLE public.asset_pools OWNER TO admin;

--
-- Name: asset_pools_id_seq; Type: SEQUENCE; Schema: public; Owner: admin
--

ALTER TABLE public.asset_pools ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.asset_pools_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: investments; Type: TABLE; Schema: public; Owner: admin
--

CREATE TABLE public.investments (
    id bigint NOT NULL,
    investor_id bigint NOT NULL,
    trust_product_id bigint NOT NULL,
    subscription_no character varying(32) NOT NULL,
    amount numeric(18,2) NOT NULL,
    status character varying(32) DEFAULT 'pending'::character varying NOT NULL,
    invested_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT chk_investments_amount CHECK ((amount > (0)::numeric))
);


ALTER TABLE public.investments OWNER TO admin;

--
-- Name: investments_id_seq; Type: SEQUENCE; Schema: public; Owner: admin
--

ALTER TABLE public.investments ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.investments_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: investors; Type: TABLE; Schema: public; Owner: admin
--

CREATE TABLE public.investors (
    id bigint NOT NULL,
    code character varying(32) NOT NULL,
    name character varying(200) NOT NULL,
    investor_type character varying(32) DEFAULT 'individual'::character varying NOT NULL,
    kyc_status character varying(32) DEFAULT 'pending'::character varying NOT NULL,
    phone character varying(20),
    email character varying(200),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.investors OWNER TO admin;

--
-- Name: investors_id_seq; Type: SEQUENCE; Schema: public; Owner: admin
--

ALTER TABLE public.investors ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.investors_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: project_asset_pools; Type: TABLE; Schema: public; Owner: admin
--

CREATE TABLE public.project_asset_pools (
    id bigint NOT NULL,
    project_id bigint NOT NULL,
    asset_pool_id bigint NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.project_asset_pools OWNER TO admin;

--
-- Name: project_asset_pools_id_seq; Type: SEQUENCE; Schema: public; Owner: admin
--

ALTER TABLE public.project_asset_pools ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.project_asset_pools_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: projects; Type: TABLE; Schema: public; Owner: admin
--

CREATE TABLE public.projects (
    id bigint NOT NULL,
    code character varying(32) NOT NULL,
    name character varying(200) NOT NULL,
    description text,
    status character varying(32) DEFAULT 'draft'::character varying NOT NULL,
    address character varying(500),
    city character varying(100),
    total_budget numeric(18,2) DEFAULT 0 NOT NULL,
    planned_start_date date,
    planned_end_date date,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT chk_projects_budget CHECK ((total_budget >= (0)::numeric))
);


ALTER TABLE public.projects OWNER TO admin;

--
-- Name: projects_id_seq; Type: SEQUENCE; Schema: public; Owner: admin
--

ALTER TABLE public.projects ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.projects_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: trust_products; Type: TABLE; Schema: public; Owner: admin
--

CREATE TABLE public.trust_products (
    id bigint NOT NULL,
    asset_pool_id bigint NOT NULL,
    code character varying(32) NOT NULL,
    name character varying(200) NOT NULL,
    status character varying(32) DEFAULT 'draft'::character varying NOT NULL,
    target_amount numeric(18,2) NOT NULL,
    raised_amount numeric(18,2) DEFAULT 0 NOT NULL,
    expected_return_rate numeric(8,4),
    open_date date,
    close_date date,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT chk_trust_products_raised CHECK ((raised_amount >= (0)::numeric)),
    CONSTRAINT chk_trust_products_target CHECK ((target_amount > (0)::numeric))
);


ALTER TABLE public.trust_products OWNER TO admin;

--
-- Name: trust_products_id_seq; Type: SEQUENCE; Schema: public; Owner: admin
--

ALTER TABLE public.trust_products ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.trust_products_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Data for Name: asset_pools; Type: TABLE DATA; Schema: public; Owner: admin
--

COPY public.asset_pools (id, code, name, status, appraised_value, created_at, updated_at) FROM stdin;
1	AP-2026-00001	滨江公寓组合资产包	active	8500000.00	2026-06-21 04:47:14.030316+00	2026-06-21 04:47:14.030316+00
\.


--
-- Data for Name: investments; Type: TABLE DATA; Schema: public; Owner: admin
--

COPY public.investments (id, investor_id, trust_product_id, subscription_no, amount, status, invested_at, created_at, updated_at) FROM stdin;
1	1	1	SUB-2026-00000001	800000.00	confirmed	2026-03-05 02:30:00+00	2026-06-21 04:47:14.030316+00	2026-06-21 04:47:14.030316+00
2	2	1	SUB-2026-00000002	1200000.00	confirmed	2026-03-08 06:20:00+00	2026-06-21 04:47:14.030316+00	2026-06-21 04:47:14.030316+00
\.


--
-- Data for Name: investors; Type: TABLE DATA; Schema: public; Owner: admin
--

COPY public.investors (id, code, name, investor_type, kyc_status, phone, email, created_at, updated_at) FROM stdin;
1	INV-2026-00001	张三	individual	approved	13800000001	zhangsan@example.com	2026-06-21 04:47:14.030316+00	2026-06-21 04:47:14.030316+00
2	INV-2026-00002	明德资本	institutional	approved	021-88888888	contact@mingde-cap.com	2026-06-21 04:47:14.030316+00	2026-06-21 04:47:14.030316+00
\.


--
-- Data for Name: project_asset_pools; Type: TABLE DATA; Schema: public; Owner: admin
--

COPY public.project_asset_pools (id, project_id, asset_pool_id, created_at, updated_at) FROM stdin;
1	1	1	2026-06-21 04:47:14.030316+00	2026-06-21 04:47:14.030316+00
2	2	1	2026-06-21 04:47:14.030316+00	2026-06-21 04:47:14.030316+00
3	3	1	2026-06-21 04:47:14.030316+00	2026-06-21 04:47:14.030316+00
\.


--
-- Data for Name: projects; Type: TABLE DATA; Schema: public; Owner: admin
--

COPY public.projects (id, code, name, description, status, address, city, total_budget, planned_start_date, planned_end_date, created_at, updated_at) FROM stdin;
1	PRJ-2026-00001	上海浦东滨江公寓 A 栋装修	\N	in_progress	上海市浦东新区滨江大道 100 号 A 栋	上海	3200000.00	2026-01-10	2026-06-30	2026-06-21 04:47:14.030316+00	2026-06-21 04:47:14.030316+00
2	PRJ-2026-00002	上海浦东滨江公寓 B 栋装修	\N	in_progress	上海市浦东新区滨江大道 100 号 B 栋	上海	2800000.00	2026-02-01	2026-07-31	2026-06-21 04:47:14.030316+00	2026-06-21 04:47:14.030316+00
3	PRJ-2026-00003	上海浦东滨江公寓地下车库改造	\N	completed	上海市浦东新区滨江大道 100 号 地下一层	上海	1500000.00	2025-10-01	2026-01-31	2026-06-21 04:47:14.030316+00	2026-06-21 04:47:14.030316+00
\.


--
-- Data for Name: trust_products; Type: TABLE DATA; Schema: public; Owner: admin
--

COPY public.trust_products (id, asset_pool_id, code, name, status, target_amount, raised_amount, expected_return_rate, open_date, close_date, created_at, updated_at) FROM stdin;
1	1	TRU-2026-00001	滨江公寓信托一期	raising	5000000.00	2000000.00	0.0650	2026-03-01	2026-06-30	2026-06-21 04:47:14.030316+00	2026-06-21 04:47:14.030316+00
\.


--
-- Name: asset_pools_id_seq; Type: SEQUENCE SET; Schema: public; Owner: admin
--

SELECT pg_catalog.setval('public.asset_pools_id_seq', 1, true);


--
-- Name: investments_id_seq; Type: SEQUENCE SET; Schema: public; Owner: admin
--

SELECT pg_catalog.setval('public.investments_id_seq', 2, true);


--
-- Name: investors_id_seq; Type: SEQUENCE SET; Schema: public; Owner: admin
--

SELECT pg_catalog.setval('public.investors_id_seq', 2, true);


--
-- Name: project_asset_pools_id_seq; Type: SEQUENCE SET; Schema: public; Owner: admin
--

SELECT pg_catalog.setval('public.project_asset_pools_id_seq', 3, true);


--
-- Name: projects_id_seq; Type: SEQUENCE SET; Schema: public; Owner: admin
--

SELECT pg_catalog.setval('public.projects_id_seq', 3, true);


--
-- Name: trust_products_id_seq; Type: SEQUENCE SET; Schema: public; Owner: admin
--

SELECT pg_catalog.setval('public.trust_products_id_seq', 1, true);


--
-- Name: asset_pools asset_pools_pkey; Type: CONSTRAINT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.asset_pools
    ADD CONSTRAINT asset_pools_pkey PRIMARY KEY (id);


--
-- Name: investments investments_pkey; Type: CONSTRAINT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.investments
    ADD CONSTRAINT investments_pkey PRIMARY KEY (id);


--
-- Name: investors investors_pkey; Type: CONSTRAINT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.investors
    ADD CONSTRAINT investors_pkey PRIMARY KEY (id);


--
-- Name: project_asset_pools project_asset_pools_pkey; Type: CONSTRAINT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.project_asset_pools
    ADD CONSTRAINT project_asset_pools_pkey PRIMARY KEY (id);


--
-- Name: projects projects_pkey; Type: CONSTRAINT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.projects
    ADD CONSTRAINT projects_pkey PRIMARY KEY (id);


--
-- Name: trust_products trust_products_pkey; Type: CONSTRAINT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.trust_products
    ADD CONSTRAINT trust_products_pkey PRIMARY KEY (id);


--
-- Name: asset_pools uq_asset_pools_code; Type: CONSTRAINT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.asset_pools
    ADD CONSTRAINT uq_asset_pools_code UNIQUE (code);


--
-- Name: investments uq_investments_subscription_no; Type: CONSTRAINT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.investments
    ADD CONSTRAINT uq_investments_subscription_no UNIQUE (subscription_no);


--
-- Name: investors uq_investors_code; Type: CONSTRAINT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.investors
    ADD CONSTRAINT uq_investors_code UNIQUE (code);


--
-- Name: project_asset_pools uq_project_asset_pools; Type: CONSTRAINT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.project_asset_pools
    ADD CONSTRAINT uq_project_asset_pools UNIQUE (project_id, asset_pool_id);


--
-- Name: projects uq_projects_code; Type: CONSTRAINT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.projects
    ADD CONSTRAINT uq_projects_code UNIQUE (code);


--
-- Name: trust_products uq_trust_products_code; Type: CONSTRAINT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.trust_products
    ADD CONSTRAINT uq_trust_products_code UNIQUE (code);


--
-- Name: idx_asset_pools_status; Type: INDEX; Schema: public; Owner: admin
--

CREATE INDEX idx_asset_pools_status ON public.asset_pools USING btree (status);


--
-- Name: idx_investments_invested_at; Type: INDEX; Schema: public; Owner: admin
--

CREATE INDEX idx_investments_invested_at ON public.investments USING btree (invested_at DESC);


--
-- Name: idx_investments_investor_id; Type: INDEX; Schema: public; Owner: admin
--

CREATE INDEX idx_investments_investor_id ON public.investments USING btree (investor_id);


--
-- Name: idx_investments_status; Type: INDEX; Schema: public; Owner: admin
--

CREATE INDEX idx_investments_status ON public.investments USING btree (status);


--
-- Name: idx_investments_trust_product_id; Type: INDEX; Schema: public; Owner: admin
--

CREATE INDEX idx_investments_trust_product_id ON public.investments USING btree (trust_product_id);


--
-- Name: idx_investors_kyc_status; Type: INDEX; Schema: public; Owner: admin
--

CREATE INDEX idx_investors_kyc_status ON public.investors USING btree (kyc_status);


--
-- Name: idx_investors_type; Type: INDEX; Schema: public; Owner: admin
--

CREATE INDEX idx_investors_type ON public.investors USING btree (investor_type);


--
-- Name: idx_project_asset_pools_asset_pool_id; Type: INDEX; Schema: public; Owner: admin
--

CREATE INDEX idx_project_asset_pools_asset_pool_id ON public.project_asset_pools USING btree (asset_pool_id);


--
-- Name: idx_project_asset_pools_project_id; Type: INDEX; Schema: public; Owner: admin
--

CREATE INDEX idx_project_asset_pools_project_id ON public.project_asset_pools USING btree (project_id);


--
-- Name: idx_projects_city; Type: INDEX; Schema: public; Owner: admin
--

CREATE INDEX idx_projects_city ON public.projects USING btree (city);


--
-- Name: idx_projects_status; Type: INDEX; Schema: public; Owner: admin
--

CREATE INDEX idx_projects_status ON public.projects USING btree (status);


--
-- Name: idx_trust_products_asset_pool_id; Type: INDEX; Schema: public; Owner: admin
--

CREATE INDEX idx_trust_products_asset_pool_id ON public.trust_products USING btree (asset_pool_id);


--
-- Name: idx_trust_products_status; Type: INDEX; Schema: public; Owner: admin
--

CREATE INDEX idx_trust_products_status ON public.trust_products USING btree (status);


--
-- Name: asset_pools trg_asset_pools_updated_at; Type: TRIGGER; Schema: public; Owner: admin
--

CREATE TRIGGER trg_asset_pools_updated_at BEFORE UPDATE ON public.asset_pools FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: investments trg_investments_updated_at; Type: TRIGGER; Schema: public; Owner: admin
--

CREATE TRIGGER trg_investments_updated_at BEFORE UPDATE ON public.investments FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: investors trg_investors_updated_at; Type: TRIGGER; Schema: public; Owner: admin
--

CREATE TRIGGER trg_investors_updated_at BEFORE UPDATE ON public.investors FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: project_asset_pools trg_project_asset_pools_updated_at; Type: TRIGGER; Schema: public; Owner: admin
--

CREATE TRIGGER trg_project_asset_pools_updated_at BEFORE UPDATE ON public.project_asset_pools FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: projects trg_projects_updated_at; Type: TRIGGER; Schema: public; Owner: admin
--

CREATE TRIGGER trg_projects_updated_at BEFORE UPDATE ON public.projects FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: trust_products trg_trust_products_updated_at; Type: TRIGGER; Schema: public; Owner: admin
--

CREATE TRIGGER trg_trust_products_updated_at BEFORE UPDATE ON public.trust_products FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: investments investments_investor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.investments
    ADD CONSTRAINT investments_investor_id_fkey FOREIGN KEY (investor_id) REFERENCES public.investors(id);


--
-- Name: investments investments_trust_product_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.investments
    ADD CONSTRAINT investments_trust_product_id_fkey FOREIGN KEY (trust_product_id) REFERENCES public.trust_products(id);


--
-- Name: project_asset_pools project_asset_pools_asset_pool_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.project_asset_pools
    ADD CONSTRAINT project_asset_pools_asset_pool_id_fkey FOREIGN KEY (asset_pool_id) REFERENCES public.asset_pools(id);


--
-- Name: project_asset_pools project_asset_pools_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.project_asset_pools
    ADD CONSTRAINT project_asset_pools_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id);


--
-- Name: trust_products trust_products_asset_pool_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.trust_products
    ADD CONSTRAINT trust_products_asset_pool_id_fkey FOREIGN KEY (asset_pool_id) REFERENCES public.asset_pools(id);


--
-- PostgreSQL database dump complete
--

\unrestrict wY77mSb5ix07ymW5CbnhdEvUYBERxgmrtgHmdp9LdShOxn4OMBW8EmnY38j8mjP

