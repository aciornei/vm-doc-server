# Șablon serviciu IT – Keycloak – Identity & SSO

> Varianta într-un singur fișier. În Outline, separă fiecare secțiune de nivel 2 într-un document-părinte; subdocumentele sunt în arhiva ZIP.

## 01 – Fișa serviciului
*Scop, responsabil, criticitate, utilizatori și SLA*

## Identificare
- **Cod serviciu:** SVC-IAM-001 (de confirmat)
- **Denumire:** Keycloak – Identity & SSO
- **Descriere și scop:** [Ce furnizează serviciul și cui]
- **Mediu:** [PROD / TEST / DEV]
- **Stare:** [Activ / În mentenanță / Retras]
- **Responsabil tehnic:** [Nume/echipă]
- **Proprietar serviciu:** [Nume/echipă]
- **Criticitate:** [Ridicată / Medie / Scăzută]
- **Program suport / SLA / RTO / RPO:** [De completat sau link către politica oficială]

## Utilizatori și consumatori
- **Categorii utilizatori:** [Angajați, administratori, aplicații]
- **Servicii consumatoare:** [Link spre registrul de relații GLPI / VM-DOC; nu duplicăm lista]

## Linkuri operaționale
- **GLPI / CMDB:** [URL]
- **VM-DOC (serviciu):** [URL]
- **Monitorizare:** [URL]
- **Backup / Veeam:** [URL]
- **Vault:** [Referință, fără parole]
- **Huly / proiect:** [URL]

## Responsabilitatea reviziei
- **Ultima verificare:** [AAAA-LL-ZZ]
- **Verificat de:** [Persoană]
- **Următoarea revizie:** [AAAA-LL-ZZ]

---

## 02 – Arhitectură și dependențe
*Arhitectură logică, diagramă și dependențe*

## Rezumat arhitectural
[Descrie fluxul browser → reverse proxy → Keycloak → AD/LDAP și componenta DB.]

## Diagrama
[Inserează diagramă sau link către diagramă.]

## Componente și dependențe
- **Instanțe și medii:** [Link către VM-DOC]
- **Identity source:** [AD / LDAP și descriere integrare]
- **Bază de date:** [Referință serviciu / link]
- **Reverse proxy / TLS:** [Referință serviciu / link]
- **DNS / certificate:** [Linkuri relevante]
- **Dependențe și impact:** [Link GLPI / VM-DOC – sursa de adevăr]

## Fluxuri critice
[SSO OIDC / SAML / Kerberos, la nivel conceptual.]

---

## 03 – Configurare
*Configurația curentă a serviciului; detaliile în subpagini*

## Scopul secțiunii
Conține configurația **curentă**, validată, fără secrete. Procedurile de schimbare sunt în 05 – Proceduri.

## Configurație de ansamblu
- **Versiune Keycloak:** [Versiunea în producție]
- **Realm(uri):** [Nume]
- **Metode de autentificare:** [OIDC / SAML / Kerberos / LDAP]
- **Loc configurație:** [URL repo / referință / document tehnic]

## Subdocumente
- Configurare realm AD
- Integrare AD / Kerberos
- Integrare Grafana OIDC
- Mapperi și client scopes

## Reguli
Documentează aici ce este activ. Nu include parole, client secrets sau chei private.

---

## 04 – Operare și mentenanță
*Rutine, monitorizare și verificări*

## Verificări operaționale
| Verificare | Frecvență | Instrument / link | Rezultat așteptat |
|---|---|---|---|
| Disponibilitate endpoint | [Zilnic] | [Grafana/Blackbox] | [OK] |
| Erori autentificare | [Zilnic] | [Loguri/Graylog] | [Fără creșteri anormale] |
| Certificate | [Săptămânal] | [Monitorizare] | [Fără expirări apropiate] |
| Backup | [Zilnic] | [Veeam] | [Job reușit] |

## Operare normală
- **Pornire / oprire:** [Referință runbook]
- **Locația logurilor:** [Referință sau URL]
- **Monitorizare:** [URL]
- **Mentenanță planificată:** [Interval / responsabil]
- **Escaladare:** [Persoane / echipe, fără date sensibile]

---

## 05 – Proceduri (Runbooks)
*Proceduri pas cu pas, cu verificare și rollback*

## Scop
Proceduri operaționale care pot fi executate repetabil de către un administrator autorizat.

## Catalog proceduri
- Adăugare client OIDC
- Upgrade Keycloak
- Înlocuire certificat
- Restaurare serviciu

## Cerințe pentru fiecare runbook
1. Scop și situații de utilizare
2. Precondiții și aprobări
3. Riscuri și impact
4. Pași numerotați
5. Verificări de succes
6. Rollback
7. Referințe la change și responsabil

---

## 06 – Utilizare și administrare
*Instrucțiuni și operații administrative*

## Pentru administratori
- [Cum se accesează consola de administrare]
- [Cum se investighează o autentificare nereușită]
- [Cum se verifică un client / utilizator / grup]

## Pentru utilizatori
- [Autentificare în aplicații]
- [Resetare parolă – trimitere către procedura AD, dacă este cazul]
- [Probleme frecvente și canal de suport]

## Acces și roluri
[Descrie rolurile autorizate, fără date de acces.]

---

## 07 – Incidente și probleme cunoscute
*Simptome, cauze, diagnostic și soluții reutilizabile*

## Cum folosim această secțiune
Aici păstrăm **articole reutilizabile**, nu câte o copie a fiecărui incident. Tichetele rămân în sistemul operațional.

## Index probleme
- Invalid parameter: redirect_uri
- Eroare Kerberos / SPNEGO
- Eroare de sincronizare utilizator

## Diagnostic rapid
- **Stare serviciu:** [Link]
- **Loguri:** [Link]
- **Validare certificat:** [Pași / link]
- **Escaladare:** [Echipă]

---

## 08 – Change & Release
*Istoricul schimbărilor semnificative și versiunile*

## Stare curentă
- **Versiune în PROD:** [x.y.z]
- **Data ultimei schimbări:** [AAAA-LL-ZZ]
- **Sursa oficială a change-urilor:** [Huly / alt sistem]

## Schimbări semnificative
| Data | Change | Rezumat | Impact | Link tichet |
|---|---|---|---|---|
| [AAAA-LL-ZZ] | [CHG-...] | [Ce s-a schimbat] | [Impact] | [URL] |

## Reguli
Nu duplica întregul tichet. Păstrează aici doar decizia tehnică, impactul, pașii de validare și legătura către change.

---

## 09 – Securitate și continuitate
*Control acces, audit, backup și DR*

## Controlul accesului
- **Administratori autorizați:** [Roluri/echipe]
- **Autentificare administrare:** [Politică MFA/SSO]
- **Audit și loguri:** [Link]
- **Politici aplicate:** [Link la standarde comune]

## Secrete și certificate
- **Locația secretelor:** [Referințe Vault; fără valori]
- **Gestionarea certificatelor:** [Procedură / responsabil]

## Continuitate
- **Backup:** [Politică + link sistem]
- **RTO / RPO:** [Valori aprobate]
- **Scenarii DR:** [Descriere]
- **Ultimul test restaurare:** [Dată + rezultat + link]

---

## 10 – Istoric și arhivă
*Documente înlocuite, cu marcajul de neutilizare*

## Reguli arhivare
Documentele păstrate aici au valoare istorică, dar **nu sunt instrucțiuni valabile pentru producție**.

## Evidență
| Document | Perioada de valabilitate | Înlocuit de | Motivul arhivării |
|---|---|---|---|
| [Titlu] | [Perioadă] | [Link] | [Motiv] |

> Atenție: nu restaura configurații sau executa comenzi din arhivă fără validare.

---
