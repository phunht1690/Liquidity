"use strict";
(() => {
  const byId=id=>document.getElementById(id);
  const hero=byId("company-hero"),logo=byId("company-logo"),cover=byId("company-cover");
  if(!hero||!logo||!cover)return;
  const details=byId('company-details'),detailsToggle=byId('company-details-toggle');
  if(details&&detailsToggle)detailsToggle.addEventListener('click',()=>{
    const expanded=window.lopmDisclosure?window.lopmDisclosure.toggle(details):details.hidden;
    if(!window.lopmDisclosure)details.hidden=!expanded;
    detailsToggle.setAttribute('aria-expanded',String(expanded));
    detailsToggle.textContent=expanded?'Thu gọn thông tin':'Thông tin doanh nghiệp';
  });
  const photoSource=document.createElement("a");photoSource.className="company-photo-source";photoSource.hidden=true;photoSource.target="_blank";photoSource.rel="noopener noreferrer";hero.append(photoSource);
  const coverBrand=document.createElement("div"),coverBrandImage=document.createElement("img");
  coverBrand.className="company-cover-brand";coverBrand.hidden=true;coverBrand.setAttribute("aria-hidden","true");coverBrandImage.alt="";coverBrandImage.decoding="async";coverBrand.append(coverBrandImage);hero.append(coverBrand);
  const placeholder=byId("company-logo-placeholder"),sector=byId("company-sector"),website=byId("company-website"),business=byId("company-business"),location=byId("company-location");
  let companies=null,pending=null,selection=null,revision=0,signature="";
  const localAsset=value=>typeof value==="string"&&/^\/assets\/companies\/(logos|covers)\/[A-Z0-9]{2,6}-[a-f0-9]{10}\.(jpg|jpeg|png|webp|avif|svg|gif|bmp)$/.test(value)?value:null;
  function hideImage(element){element.hidden=true;element.classList.remove("is-loaded");element.onload=null;element.onerror=null;element.removeAttribute("src");delete element.dataset.asset;}
  function showImage(element,path,version,onVisible){
    path=localAsset(path);
    if(!path){hideImage(element);return;}
    if(element.dataset.asset===path&&element.complete&&element.naturalWidth>0){element.hidden=false;element.classList.add("is-loaded");onVisible?.();return;}
    element.hidden=true;element.classList.remove("is-loaded");element.dataset.asset=path;
    element.onload=()=>{if(version!==revision||element.dataset.asset!==path)return;element.hidden=false;requestAnimationFrame(()=>element.classList.add("is-loaded"));onVisible?.();};
    element.onerror=()=>{if(version!==revision)return;hideImage(element);};
    element.src=path;
  }
  function apply(version){
    if(version!==revision||!selection)return;
    const entry=companies?.[selection.symbol];
    hero.dataset.company=selection.symbol;
    const graphic=entry?.cover_kind==="brand_graphic";
    const office=entry?.cover_kind==="headquarters";
    hero.dataset.media=graphic?"brand":office?"headquarters":"business";
    if(business){business.textContent=entry?.business||"";business.hidden=!business.textContent;}
    if(location){location.textContent=office?entry?.headquarters?.label||"":entry?.cover_label||entry?.headquarters?.label||"";location.title=office?entry?.headquarters?.address||"":entry?.cover_subject||"";location.hidden=!location.textContent;}
    sector.textContent=selection.sector||entry?.sector||"";sector.hidden=!sector.textContent;
    logo.alt=`${entry?.logo_kind==='official_wordmark_banner'?'Nhận diện':'Logo'} ${selection.name||entry?.name||selection.symbol}`;
    logo.title=entry?.logo_brand_status==='legacy_same_issuer'?"Nhận diện đã công bố trước đây của cùng doanh nghiệp":"";
    placeholder.hidden=false;
    showImage(logo,entry?.logo,version,()=>{placeholder.hidden=true;});
    const photo=localAsset(entry?.cover),brand=localAsset(entry?.logo);
    hero.dataset.photo=photo?graphic?"brand":"available":"missing";
    cover.alt=photo?(entry.cover_subject||(graphic?"Nền nhận diện doanh nghiệp":office?"Trụ sở doanh nghiệp":"Hoạt động doanh nghiệp")):"";
    cover.setAttribute("aria-hidden",photo?"false":"true");
    if(photo&&!graphic)hero.style.setProperty("--hq-photo",`url("${photo}")`);else hero.style.removeProperty("--hq-photo");
    cover.classList.toggle("is-brand-backdrop",!photo);
    showImage(cover,photo||brand,version);
    cover.style.objectPosition=/^\d{1,3}% \d{1,3}%$/.test(entry?.cover_position||"")?entry.cover_position:"center 48%";
    cover.style.objectFit=photo?"cover":"contain";
    cover.title=entry?.cover_subject||"";
    hero.style.setProperty("--company-accent",/^#[a-f0-9]{6}$/i.test(entry?.accent||"")?entry.accent:"#88bca2");
    hero.style.setProperty("--logo-bg",/^#[a-f0-9]{6}$/i.test(entry?.logo_background||"")?entry.logo_background:"#ffffff");
    coverBrand.hidden=true;
    if(photo&&!graphic&&!office&&brand)showImage(coverBrandImage,brand,version,()=>{coverBrand.hidden=false;});else hideImage(coverBrandImage);
    photoSource.hidden=true;photoSource.removeAttribute("href");
    try{
      const source=new URL(entry?.photo_source_url);
      if(photo&&!graphic&&["https:","http:"].includes(source.protocol)){
        const fullCredit=entry.photo_credit||"",license=fullCredit.match(/CC BY(?:-SA)?\s*[\d.]+/i)?.[0]||"";
        const author=fullCredit.split(";")[0].split("http")[0].trim().replace(/[;·|]+$/,"").trim();
        const credit=author+(license&&!author.includes(license)?` · ${license}`:"");
        const illustration=entry.business_image_kind&&entry.business_image_kind!=="photograph"||entry.headquarters?.image_kind==="architectural_rendering";
        photoSource.href=source.href;photoSource.textContent=credit?`${illustration?'Hình':'Ảnh'}: ${credit} ↗`:"Nguồn hình ↗";photoSource.title=entry.photo_credit||"Mở nguồn hình và bối cảnh doanh nghiệp";photoSource.hidden=false;
      }
    }catch{}
    website.hidden=true;website.removeAttribute("href");
    try{
      const url=new URL(entry?.website);
      if(["https:","http:"].includes(url.protocol)){
        website.href=url.href;website.hidden=false;
        website.title=`${selection.name||entry.name} · ${url.hostname}`;
      }
    }catch{}
  }
  function load(){
    if(companies)return Promise.resolve(companies);
    if(!pending)pending=fetch("/assets/companies/manifest.json",{cache:"no-cache"}).then(response=>{
      if(!response.ok)throw new Error("media_unavailable");return response.json();
    }).then(data=>{companies=data.companies||{};return companies;}).catch(()=>null).finally(()=>{pending=null;});
    return pending;
  }
  function clear(){
    revision++;signature="";selection=null;hideImage(logo);hideImage(cover);hideImage(coverBrandImage);coverBrand.hidden=true;photoSource.hidden=true;photoSource.removeAttribute("href");
    placeholder.hidden=false;sector.hidden=true;website.hidden=true;if(business){business.hidden=true;business.textContent="";}if(location){location.hidden=true;location.textContent="";}hero.removeAttribute("data-company");hero.removeAttribute("data-media");hero.removeAttribute("data-photo");hero.style.removeProperty("--hq-photo");hero.style.removeProperty("--logo-bg");
  }
  function show(symbol,name,group){
    if(!symbol){clear();return;}
    const next=JSON.stringify([symbol,name,group]);
    if(next===signature&&companies)return;
    signature=next;selection={symbol,name,sector:group};const version=++revision;
    apply(version);if(!companies)load().then(()=>apply(version));
  }
  function preview(symbol,universe){
    if(!symbol){clear();return;}
    show(symbol);
    const version=revision;
    const identity=()=>{
      if(version!==revision)return;
      const entry=companies?.[symbol];
      if(!entry)return;
      const heading=byId("stock-heading"),name=byId("stock-name");
      if(heading)heading.textContent=symbol;
      const label=({HNX_PILOT:"HNX · thử nghiệm",UPCOM_PILOT:"UPCoM · thử nghiệm"})[universe]||universe;
      if(name)name.textContent=`${entry.name}${label?` · ${label}`:""}`;
    };
    identity();if(!companies)load().then(identity);
  }
  window.lopmCompanyMedia={show,clear,preview};
  load();
})();
