// import latest release from npm repository 
import { InfluxDB, Point } from 'https://unpkg.com/@influxdata/influxdb-client/dist/index.browser.mjs'
// import {PingAPI, SetupAPI} from 'https://unpkg.com/@influxdata/influxdb-client-apis/dist/index.browser.mjs'
// or use the following imports to use local builds
// import {InfluxDB, Point} from '../packages/core/dist/index.browser.mjs'
import { PingAPI, SetupAPI } from '../packages/apis/dist/index.browser.mjs'

/**
  * Import the configuration from ./env_browser.js.
  * The property INFLUX_ENV.bucket is only used in onboardingExample() and writeExample().
  * To prevent SQL injection attacks, the variable is not used within the Flux query examples.
  * The query examples assume your InfluxDB bucket is named "my-bucket".
  */
import './env_browser.js'
const { url, token, org, bucket, username, password } = window.INFLUX_ENV

const influxDB = new InfluxDB({ url, token })

// log results also to HTML page
const logField = document.getElementById('log');
function log(message, ...rest) {
    console.log(arguments[0], rest)
    const previousValue = logField.value
    logField.value += (previousValue ? '\n' : '') + Array.prototype.slice.call(arguments).join('\n')
    // scroll to bottom with latest results
    logField.scrollTo(0, logField.scrollHeight <= logField.offsetHeight ? 0 : logField.scrollHeight - logField.offsetHeight)
}

function writeExample(value) {
    const writeApi = influxDB.getWriteApi(org, bucket)
    // setup default tags for all writes through this API
    writeApi.useDefaultTags({ location: 'browser' })

    log('\n*** WRITE ***')
    const point1 = new Point('temperature')
        .tag('example', 'index.html')
        .floatField('value', value)
    writeApi.writePoint(point1)
    log(` ${point1.toLineProtocol()}`)

    // flush pending writes and close writeApi
    writeApi
        .close()
        .then(() => {
            log('WRITE FINISHED')
            temperatureInput.value = String(20 + Math.round(100 * Math.random()) / 10)
        })
        .catch(e => {
            log('WRITE FAILED', e)
        })
}
function queryExample(fluxQuery) {
    log('\n*** QUERY ***')
    const queryApi = influxDB.getQueryApi(org)
    queryApi.queryRows(fluxQuery, {
        next(row, tableMeta) {
            const o = tableMeta.toObject(row)
            if (o.example) {
                // custom output for example query
                log(
                    `${o._time} ${o._measurement} in '${o.location}' (${o.example}): ${o._field}=${o._value}`
                )
            } else {
                // default output
                log(JSON.stringify(o, null, 2))
            }
        },
        error(error) {
            log('QUERY FAILED', error)
        },
        complete() {
            log('QUERY FINISHED')
        },
    })
}
function onboardingExample() {
    log('\n*** ONBOARDING ***')
    const setupApi = new SetupAPI(influxDB)
    setupApi
        .getSetup()
        .then(async ({ allowed }) => {
            if (allowed) {
                await setupApi.postSetup({
                    body: {
                        org,
                        bucket,
                        username,
                        password,
                        token
                    }
                })
                log(`InfluxDB '${url}' is now onboarded.`)
            } else {
                log(`InfluxDB '${url}' has been already onboarded.`)
            }
        })
        .catch(error => {
            log('Onboarding FAILED', error)
        })
}
function pingExample() {
    log('\n*** PING ***')
    const pingApi = new PingAPI(influxDB)
    pingApi
        .getPing()
        .then(() => {
            log('Ping SUCCESS')
        })
        .catch(error => {
            log('Ping FAILED', error)
        })
}

// initialize page controls
const temperatureInput = document.getElementById('temperature');
temperatureInput.value = String(20 + Math.round(100 * Math.random()) / 10)
const writeButton = document.getElementById('writeButton')
writeButton.addEventListener('click', () => {
    const number = Number(temperatureInput.value)
    if (isNaN(number)) log('ERROR: Not a number ' + temperatureInput.value);
    else writeExample(number)
})
const queryInput = document.getElementById('query');
const fluxQueryParam = new URLSearchParams(window.location.search).get('fluxQuery');
if (fluxQueryParam) {
    queryInput.value = fluxQueryParam
}
document.getElementById('queryButton').addEventListener('click', () => {
    queryExample(queryInput.value)
})
document.getElementById('onboardButton').addEventListener('click', () => {
    onboardingExample()
})
document.getElementById('pingButton').addEventListener('click', () => {
    pingExample()
})
const visualizeInGiraffe = document.getElementById('visualizeInGiraffe')
visualizeInGiraffe.addEventListener('click', e => {
    const target = "./giraffe.html?fluxQuery=" + encodeURIComponent(queryInput.value)
    window.open(target, "_blank")
})