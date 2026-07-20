import { useEffect, useMemo, useState } from "react";
import CompanyList from "../components/CompanyList.jsx";
import FormulaEditor from "../components/FormulaEditor.jsx";
import FieldPickerModal from "../components/FieldPickerModal.jsx";
import CreateCompanyModal from "../components/CreateCompanyModal.jsx";
import CreateFieldModal from "../components/CreateFieldModal.jsx";
import {
  fetchCanonicalFields,
  fetchCompanies,
  getCompany,
  saveCompany,
} from "../api.js";

function deepCopy(value) {
  return JSON.parse(JSON.stringify(value));
}

export default function ManagePage() {
  const [companies, setCompanies] = useState([]);
  const [companiesLoading, setCompaniesLoading] = useState(true);
  const [companiesError, setCompaniesError] = useState("");

  const [canonicalFields, setCanonicalFields] = useState([]);

  const [selectedId, setSelectedId] = useState(null);
  const [config, setConfig] = useState(null);
  const [loadedConfig, setLoadedConfig] = useState(null);
  const [configLoading, setConfigLoading] = useState(false);
  const [configError, setConfigError] = useState("");

  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [saveOk, setSaveOk] = useState(false);

  const [showCreateCompany, setShowCreateCompany] = useState(false);
  const [showFieldPicker, setShowFieldPicker] = useState(false);
  const [showCreateField, setShowCreateField] = useState(false);

  const fieldsByKey = useMemo(() => {
    const map = {};
    for (const f of canonicalFields) map[f.key] = f;
    return map;
  }, [canonicalFields]);

  const dirty = useMemo(() => {
    if (!config || !loadedConfig) return false;
    return JSON.stringify(config.components) !== JSON.stringify(loadedConfig.components);
  }, [config, loadedConfig]);

  async function loadCompanies() {
    setCompaniesLoading(true);
    setCompaniesError("");
    try {
      setCompanies(await fetchCompanies());
    } catch (err) {
      setCompaniesError(err.message || "โหลดรายชื่อบริษัทไม่สำเร็จ");
    } finally {
      setCompaniesLoading(false);
    }
  }

  async function loadCanonicalFields() {
    try {
      setCanonicalFields(await fetchCanonicalFields());
    } catch {
      // Non-fatal for browsing; the picker will simply show nothing until reload.
      setCanonicalFields([]);
    }
  }

  useEffect(() => {
    loadCompanies();
    loadCanonicalFields();
  }, []);

  async function selectCompany(companyId) {
    setSelectedId(companyId);
    setConfig(null);
    setConfigError("");
    setSaveError("");
    setSaveOk(false);
    setConfigLoading(true);
    try {
      const loaded = await getCompany(companyId);
      setConfig(loaded);
      setLoadedConfig(deepCopy(loaded));
    } catch (err) {
      setConfigError(err.message || "โหลดสูตรบริษัทไม่สำเร็จ");
    } finally {
      setConfigLoading(false);
    }
  }

  function updateComponents(nextComponents) {
    setConfig((prev) => ({ ...prev, components: nextComponents }));
    setSaveOk(false);
    setSaveError("");
  }

  function onChangeComponent(index, patch) {
    updateComponents(config.components.map((c, i) => (i === index ? { ...c, ...patch } : c)));
  }

  function onRemoveComponent(index) {
    updateComponents(config.components.filter((_, i) => i !== index));
  }

  function onPickField(fieldKey) {
    const field = fieldsByKey[fieldKey];
    const sign = field && field.polarity === "deduction" ? "-" : "+";
    updateComponents([...config.components, { field: fieldKey, sign, required: false }]);
    setShowFieldPicker(false);
  }

  async function onSave() {
    if (saving || !config) return;
    setSaving(true);
    setSaveError("");
    setSaveOk(false);
    try {
      const saved = await saveCompany(config.company_id, {
        display_name: config.display_name,
        components: config.components,
      });
      setConfig(saved);
      setLoadedConfig(deepCopy(saved));
      setSaveOk(true);
    } catch (err) {
      setSaveError(err.message || "บันทึกสูตรไม่สำเร็จ");
    } finally {
      setSaving(false);
    }
  }

  function onReset() {
    setConfig(deepCopy(loadedConfig));
    setSaveError("");
    setSaveOk(false);
  }

  function onCompanyCreated(created) {
    setShowCreateCompany(false);
    setCompanies((prev) => {
      const without = prev.filter((c) => c.company_id !== created.company_id);
      return [...without, { company_id: created.company_id, display_name: created.display_name }];
    });
    setSelectedId(created.company_id);
    setConfig(created);
    setLoadedConfig(deepCopy(created));
    setConfigError("");
    setSaveOk(false);
  }

  async function onFieldCreated() {
    setShowCreateField(false);
    await loadCanonicalFields(); // make the new field pickable
    setShowFieldPicker(true);
  }

  const usedFields = useMemo(
    () => new Set(config ? config.components.map((c) => c.field) : []),
    [config]
  );

  return (
    <>
      <div className="page-head">
        <h1>จัดการสูตรบริษัท</h1>
        <p>แก้ไขสูตรคำนวณ SSO ของแต่ละบริษัท เพิ่มบริษัทใหม่ หรือเพิ่ม field กลางใหม่</p>
      </div>

      <div className="manage-grid">
        <CompanyList
          companies={companies}
          loading={companiesLoading}
          error={companiesError}
          selectedId={selectedId}
          onSelect={selectCompany}
          onReload={loadCompanies}
          onCreateClick={() => setShowCreateCompany(true)}
        />

        <div className="manage-right">
          {!selectedId ? (
            <div className="card center-state">← เลือกบริษัทจากรายการเพื่อแก้ไขสูตร</div>
          ) : configLoading ? (
            <div className="card center-state">
              <span className="spinner spinner-dark" /> กำลังโหลดสูตร…
            </div>
          ) : configError ? (
            <div className="card">
              <div className="banner banner-error" role="alert">
                {configError}{" "}
                <button className="link" onClick={() => selectCompany(selectedId)}>
                  ลองอีกครั้ง
                </button>
              </div>
            </div>
          ) : config ? (
            <FormulaEditor
              config={config}
              fieldsByKey={fieldsByKey}
              dirty={dirty}
              saving={saving}
              saveError={saveError}
              saveOk={saveOk}
              onChangeComponent={onChangeComponent}
              onRemoveComponent={onRemoveComponent}
              onAddComponentClick={() => setShowFieldPicker(true)}
              onSave={onSave}
              onReset={onReset}
            />
          ) : null}
        </div>
      </div>

      {showCreateCompany && (
        <CreateCompanyModal
          onClose={() => setShowCreateCompany(false)}
          onCreated={onCompanyCreated}
        />
      )}

      {showFieldPicker && (
        <FieldPickerModal
          canonicalFields={canonicalFields}
          usedFields={usedFields}
          onPick={onPickField}
          onClose={() => setShowFieldPicker(false)}
          onCreateFieldClick={() => {
            setShowFieldPicker(false);
            setShowCreateField(true);
          }}
        />
      )}

      {showCreateField && (
        <CreateFieldModal
          onClose={() => setShowCreateField(false)}
          onCreated={onFieldCreated}
        />
      )}
    </>
  );
}
