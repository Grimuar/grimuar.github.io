// Единый контакт сайта; HTML сохраняет резервный адрес без JavaScript.
const siteConfig = Object.freeze({ contactEmail: "egorban.studio@gmail.com" });
document.querySelectorAll("[data-contact-email]").forEach(link => {
  link.textContent = siteConfig.contactEmail;
  link.href = "mailto:" + siteConfig.contactEmail;
});
const toggle=document.querySelector('.menu-toggle'),nav=document.querySelector('#navigation');
toggle.hidden=false;document.documentElement.classList.add('js');
function closeMenu(){toggle.setAttribute('aria-expanded','false');}
toggle.addEventListener('click',()=>toggle.setAttribute('aria-expanded',String(toggle.getAttribute('aria-expanded')!=='true')));
nav.addEventListener('click',closeMenu);document.addEventListener('keydown',e=>{if(e.key==='Escape'&&toggle.getAttribute('aria-expanded')==='true'){closeMenu();toggle.focus();}});
document.querySelectorAll('[data-year]').forEach(el=>el.textContent=new Date().getFullYear());
document.querySelectorAll('img[data-fallback]').forEach(el=>{const fallback=()=>{if(el.dataset.fallback){const src=el.dataset.fallback;delete el.dataset.fallback;el.src=src;}};el.addEventListener('error',fallback);if(el.complete&&!el.naturalWidth)fallback();});
