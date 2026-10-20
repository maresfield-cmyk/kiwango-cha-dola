(function(){var els=document.querySelectorAll('[data-live="mid"]');if(!els.length||!window.fetch)return;
var M=__MONTHS__,loc=__LOC__,last=null;
function fd(s){var p=s.split('-');return+p[2]+' '+M[+p[1]-1]+' '+p[0]}
function poll(){fetch('__BASE__api/latest.json',{cache:'no-store'}).then(function(r){return r.json()}).then(function(j){
var m=j.currencies&&j.currencies.USD&&j.currencies.USD.mid_market;if(!m||!m.rate)return;
els.forEach(function(e){e.textContent=new Intl.NumberFormat(loc,{minimumFractionDigits:2,maximumFractionDigits:2}).format(m.rate)});
document.querySelectorAll('[data-live="mid-date"]').forEach(function(e){e.textContent=fd(m.date)})}).catch(function(){})}
setInterval(function(){if(!document.hidden)poll()},300000)})();
